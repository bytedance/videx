# -*- coding: utf-8 -*-
"""
Copyright (c) 2024 Bytedance Ltd. and/or its affiliates
SPDX-License-Identifier: MIT
"""
# from sub_platforms.sql_opt.videx.videx_metadata import VidexTableStats
from sub_platforms.sql_opt.common.sample_info import SampleColumnInfo
from typing import List, Optional, Tuple, Any
import math
import pandas as pd
import logging
try:
    # Optional import for type hints; avoid hard dependency at runtime
    from sub_platforms.sql_opt.env.rds_env import Env  # type: ignore
except Exception:  # pragma: no cover
    Env = Any  # fallback typing if import is unavailable during static analysis



def load_sample_file(table_stats):
    """
    从 table_stats.sample_file_info 加载采样数据
    """
    if hasattr(table_stats, 'sample_data') and table_stats.sample_data is not None:
        logging.info(f"Using in-memory sample data for {table_stats.table_name}")
        return table_stats.sample_data

    # return None
    info = getattr(table_stats, 'sample_file_info', None)
    if not info:
        logging.info(f"No sample data available for {table_stats.table_name}")
        return None

    # Compatible with dict and objects
    if isinstance(info, dict):
        path = info.get('path') or info.get('local_path')
        fmt = (info.get('format') or 'parquet').lower()
    else:
        if getattr(info, 'local_path_prefix', None) == 'RowFetchNone':
            logging.info(f"No sample data available for {table_stats.table_name}")
            return None
        path = getattr(info, 'path', None) or getattr(info, 'local_path', None)
        fmt = (getattr(info, 'format', None) or 'parquet').lower()

    if not path:
        logging.warning(f"sample_file_info exists but no path for {table_stats.table_name}")
        return None

    try:
        if fmt == 'parquet':
            df = pd.read_parquet(path)
        elif fmt == 'csv':
            df = pd.read_csv(path)
        else:
            logging.warning(f"Unsupported sample format '{fmt}' for {table_stats.table_name}")
            return None
        logging.info(f"Loaded sample for {table_stats.table_name} from {path} shape={df.shape}")
        return df
    except Exception as e:
        logging.error(f"Failed to load sample for {table_stats.table_name} from {path}: {e}")
        return None


def calculate_optimal_buckets(samples: List[Any], data_type: str, ndv: int = None) -> int:
    """根据数据特征计算最优桶数"""
    if not samples:
        return 1
    
    n = len(samples)
    unique_count = len(set(samples))
    
    # Base number of buckets
    base_buckets = min(32, max(4, int(math.sqrt(n))))
    
    # Adjust based on the number of unique values
    if ndv:
        base_buckets = min(base_buckets, ndv)
    
    # Adjust based on the data type
    if data_type in ['int', 'bigint']:
        base_buckets = min(base_buckets * 2, 64)
    elif data_type in ['varchar', 'char', 'text']:
        base_buckets = min(base_buckets, 32)
    
    print(f"Optimal buckets: n={n}, unique={unique_count}, ndv={ndv}, result={base_buckets}")
    return max(1, base_buckets)

def block_level_sample(env: "Env", db: str, table: str, col: str,
                       rows_target: int, seed: int = 0) -> List[Any]:
    """Approximate page-level (block-level) sampling via primary-key range scanning.
    
    Strategy (avoiding full table scans):
    - Use existing metadata to estimate table size and key ranges
    - For numeric PK: use progressive sampling starting from small ranges
    - For non-numeric PK: use keyset pagination with limited OFFSET queries
    - Fallback: progressive sampling on target column
    """
    print(f"Block sampling {rows_target} rows from {db}.{table}.{col}")
    rows_target = max(1, int(rows_target))
    samples: List[Any] = []
    col_q = f"`{col}`"

    # Add sampling quality check
    max_attempts = 50
    attempt_count = 0
    consecutive_empty = 0
    
    # Heuristics for number of blocks and rows per block
    approx_block_rows = 128
    num_blocks = max(1, min(max(1, rows_target // approx_block_rows), 64))
    rows_per_block = max(1, rows_target // num_blocks)

    # Try obtain PRIMARY KEY columns
    pk_df = env.query_for_dataframe(
        f"""
        SELECT COLUMN_NAME
        FROM information_schema.statistics
        WHERE TABLE_SCHEMA = '{db}' AND TABLE_NAME = '{table}' AND INDEX_NAME = 'PRIMARY'
        ORDER BY SEQ_IN_INDEX
        """
    )

    if not pk_df.empty:
        pk_cols = [str(x) for x in pk_df['COLUMN_NAME'].tolist()]
        pk = pk_cols[0]
        pk_q = f"`{pk}`"
        
        # Try to get table metadata to estimate size without full scan
        try:
            table_meta = env.get_table_meta(db, table)
            estimated_rows = getattr(table_meta, 'rows', None) if table_meta else None
        except Exception:
            estimated_rows = None
            
        # Check if PK is numeric by attempting a small range query
        try:
            # Test with a small range to see if PK is numeric
            test_df = env.query_for_dataframe(f"SELECT {pk_q} FROM `{db}`.`{table}` WHERE {pk_q} >= 0 ORDER BY {pk_q} LIMIT 1")
            if not test_df.empty:
                test_val = test_df[pk].iloc[0]
                is_numeric = isinstance(test_val, (int, float))
            else:
                is_numeric = False
        except Exception:
            is_numeric = False

        if is_numeric:
            # Numeric PK: progressive sampling without MIN/MAX queries
            # First, try to find a reasonable starting point by sampling a few records
            start_anchor = None
            step = 1000  # Start with small steps
            
            # Try different starting points to find where data actually begins
            for test_start in [0, -1000, 1000, -10000, 10000]:
                try:
                    test_sql = f"SELECT {pk_q} FROM `{db}`.`{table}` WHERE {pk_q} >= {test_start} ORDER BY {pk_q} LIMIT 1"
                    test_df = env.query_for_dataframe(test_sql)
                    if not test_df.empty:
                        start_anchor = test_df[pk].iloc[0]
                        break
                except Exception:
                    continue
            
            # If we couldn't find a starting point, fall back to non-numeric PK method
            if start_anchor is None:
                # Fall through to non-numeric PK handling
                pass
            else:
                # Use the found starting point for progressive sampling
                current_anchor = start_anchor
                
                while len(samples) < rows_target and attempt_count < max_attempts:  # Safety limit
                    
                    attempt_count += 1
                    sql = f"SELECT {col_q} FROM `{db}`.`{table}` WHERE {col_q} IS NOT NULL AND {pk_q} >= {current_anchor} ORDER BY {pk_q} LIMIT {rows_per_block}"
                    df = env.query_for_dataframe(sql)
                    
                    if df.empty or col not in df.columns:
                        break  # No more data
                        
                    new_samples = df[col].tolist()
                    samples.extend(new_samples)

                    # Add debug information
                    print(f"Attempt {attempt_count}: got {len(new_samples)} samples, total: {len(samples)}")

                    # If we have reached the target, stop sampling
                    if len(samples) >= rows_target:
                        break

                    
                    
                    # If we got fewer rows than expected, we're near the end
                    if len(new_samples) < rows_per_block:
                        break
                        
                    # Move to next range
                    current_anchor += step
                    
                    # Dynamically adjust step size based on results
                    if len(new_samples) == rows_per_block:
                        step = min(step * 2, 10000)  # Increase step if we're getting full blocks
                    else:
                        step = max(step // 2, 100)   # Decrease step if we're getting partial blocks
                     
                    if len(new_samples) == 0:
                        consecutive_empty += 1
                        if consecutive_empty > 5:
                            print(f"Stopping sampling after {consecutive_empty} consecutive empty results")
                            break
                    else:
                        consecutive_empty = 0


                print(f"Sampling completed: {len(samples)} rows after {attempt_count} attempts")
                return samples[:rows_target]
        else:
            # Non-numeric or composite PK: use tuple keyset pagination (avoid ORDER BY target column + OFFSET)
            # NOTE: Keep original OFFSET-based anchor logic commented below for reference.
            # Use estimated rows or a reasonable default
            if estimated_rows and estimated_rows > 0:
                stride = max(1, estimated_rows // (num_blocks + 1))
            else:
                stride = 1000  # Default stride

            # Build composite PK tuple columns and ORDER BY clause
            pk_q_list = [f"`{c}`" for c in pk_cols]
            order_by = ", ".join(pk_q_list)

            for i in range(1, num_blocks + 1):
                if len(samples) >= rows_target:
                    break

                offset = (i - 1) * stride
                offset = min(offset, 100000)  # Cap offset for anchor probing only

                try:
                    # Get anchor composite PK tuple
                    anchor_cols = ", ".join(pk_q_list)
                    anchor_df = env.query_for_dataframe(
                        f"SELECT {anchor_cols} FROM `{db}`.`{table}` ORDER BY {order_by} LIMIT 1 OFFSET {offset}"
                    )
                    if anchor_df.empty:
                        continue

                    # Build tuple literal (v1, v2, ...)
                    anchor_vals = []
                    for c in pk_cols:
                        v = anchor_df[c].iloc[0]
                        if isinstance(v, str):
                            anchor_vals.append("'" + v.replace("'", "''") + "'")
                        else:
                            anchor_vals.append(str(v))
                    tuple_lit = "(" + ",".join(anchor_vals) + ")"
                    tuple_cols = "(" + ",".join(pk_q_list) + ")"

                    # Fetch block using tuple keyset pagination
                    sql = (
                        f"SELECT {col_q} FROM `{db}`.`{table}` "
                        f"WHERE {col_q} IS NOT NULL AND {tuple_cols} >= {tuple_lit} "
                        f"ORDER BY {order_by} LIMIT {rows_per_block}"
                    )
                    df = env.query_for_dataframe(sql)
                    if not df.empty and col in df.columns:
                        samples.extend(df[col].tolist())
                except Exception:
                    # If anchor probing fails, try next block
                    continue

            # Original OFFSET-based single-column PK pagination (kept for reference):
            # for i in range(1, num_blocks + 1):
            #     if len(samples) >= rows_target:
            #         break
            #     offset = (i - 1) * stride
            #     offset = min(offset, 100000)
            #     try:
            #         anchor_df = env.query_for_dataframe(
            #             f"SELECT {pk_q} AS pk FROM `{db}`.`{table}` ORDER BY {pk_q} LIMIT 1 OFFSET {offset}"
            #         )
            #         if anchor_df.empty:
            #             continue
            #         anchor = anchor_df['pk'].iloc[0]
            #         anchor_val = ("'" + anchor.replace("'", "''") + "'") if isinstance(anchor, str) else str(anchor)
            #         sql = f"SELECT {col_q} FROM `{db}`.`{table}` WHERE {col_q} IS NOT NULL AND {pk_q} >= {anchor_val} ORDER BY {pk_q} LIMIT {rows_per_block}"
            #         df = env.query_for_dataframe(sql)
            #         if not df.empty and col in df.columns:
            #             samples.extend(df[col].tolist())
            #     except Exception:
            #         continue

            return samples[:rows_target]

    # Fallback: progressive sampling on target column (no full table scan)
    start_offset = 0
    step = 1000
    
    while len(samples) < rows_target and start_offset < 100000:  # Safety limit
        # Avoid ORDER BY target column here to prevent full-table sort in fallback
        # Original (commented):
        # sql = f"SELECT {col_q} FROM `{db}`.`{table}` WHERE {col_q} IS NOT NULL ORDER BY {col_q} LIMIT {rows_per_block} OFFSET {start_offset}"
        sql = (
            f"SELECT {col_q} FROM `{db}`.`{table}` "
            f"WHERE {col_q} IS NOT NULL "
            f"LIMIT {rows_per_block} OFFSET {start_offset}"
        )
        try:
            df = env.query_for_dataframe(sql)
            if df.empty or col not in df.columns:
                break
            new_samples = df[col].tolist()
            samples.extend(new_samples)
            
            if len(new_samples) < rows_per_block:
                break
                
            start_offset += step
        except Exception:
            break
            
    return samples[:rows_target]


def validate_error(train_buckets: List[Tuple[Any, Any, int]],
                    validation_vals: List[Any]) -> float:
    """
    Compute cross-validation error per 2PHASE paper.
    
    This corresponds to the paper's cross-validation error computation:
    - Use histogram built on training set to predict validation set
    - Compute variance error (not simple L2 distance)
    - This implements the CV error part of: E[(∆CV var)²] = 2kb/r * ∑ σ²_i
    """
    if not train_buckets or not validation_vals:
        return 0.0
        
    # Get training histogram bucket counts and total
    train_total = sum(cnt for _, _, cnt in train_buckets) or 1
    train_counts = [cnt for _, _, cnt in train_buckets]
    
    # Count validation samples in each bucket
    val_counts = [0 for _ in train_buckets]
    for v in validation_vals:
        for idx, (mn, mx, _) in enumerate(train_buckets):
            if mn <= v <= mx:
                val_counts[idx] += 1
                break
    
    val_total = len(validation_vals) or 1
    
    # Compute variance error per bucket (per paper's formula)
    # For each bucket i: variance = (empirical_count - expected_count)² / expected_count
    total_variance = 0.0
    for i in range(len(train_buckets)):
        if train_counts[i] > 0:  # Avoid division by zero
            # Expected count in bucket i based on training histogram
            expected_count = (train_counts[i] / train_total) * val_total
            # Actual count in validation set
            actual_count = val_counts[i]
            # Variance contribution: (actual - expected)² / expected
            if expected_count > 0:
                variance_contrib = ((actual_count - expected_count) ** 2) / expected_count
                total_variance += variance_contrib
    
    # Return total variance error (this corresponds to ∑ σ²_i in the paper)
    return total_variance


def sort_and_validate(samples: List[Any], k: int, lmax: int,
                      histogram_builder: str = "equi-depth") -> Tuple[List[int], List[float]]:
    """Recursive sort-and-validate per 2PHASE to collect CV^2 errors per level.

    - Perform a merge-sort-like recursion on the sorted samples.
    - At each recursion level l, for each pair of sibling halves L and R:
        * Build histogram on L and validate on R; build histogram on R and validate on L.
        * Accumulate the sum of squared differences between predicted bucket probs and
          empirical bucket probs over all buckets into sq_err_levels[l].
    - Return (sample_sizes, sq_err_levels), where sample_sizes[l] corresponds to the
      training sample size used at level l (approximately n / 2^(l+1)).
    """
    if not samples:
        return [], []

    vals = sorted(samples)
    n = len(vals)
    lmax = max(1, int(lmax))

    # Accumulators per level
    sq_err_levels: List[float] = [0.0 for _ in range(lmax)]
    pair_counts: List[int] = [0 for _ in range(lmax)]

    def build_hist(vals_local: List[Any], k_local: int) -> List[Tuple[Any, Any, int]]:
        m = len(vals_local)
        if m == 0:
            return []
        k_use = max(1, int(k_local))
        step = max(1, m // k_use)
        buckets: List[Tuple[Any, Any, int]] = []
        start = 0
        while start < m:
            end = min(m, start + step)
            buckets.append((vals_local[start], vals_local[end - 1], end - start))
            start = end
        return buckets

    def rec(segment: List[Any], level: int) -> List[Any]:
        if level >= lmax or len(segment) <= 1:
            return sorted(segment)
        m = len(segment)
        mid = m // 2
        left_sorted = rec(segment[:mid], level + 1)
        right_sorted = rec(segment[mid:], level + 1)
        # build histograms and cross-validate at this level
        hl = build_hist(left_sorted, k)
        hr = build_hist(right_sorted, k)
        err = 0.0
        err += validate_error(hl, right_sorted)
        err += validate_error(hr, left_sorted)
        sq_err_levels[level] += err
        pair_counts[level] += 1
        # merge
        return merge_sorted_samples(left_sorted, right_sorted)

    rec(vals, 0)

    # Average errors per level over number of pairs
    for l in range(lmax):
        if pair_counts[l] > 0:
            sq_err_levels[l] /= float(pair_counts[l])

    # sample sizes corresponding to level l (train size ~ n / 2^(l+1))
    sample_sizes = [max(2, n // (2 ** (l + 1))) for l in range(lmax)]
    return sample_sizes, sq_err_levels


def fit_c_from_cv_curve(sample_sizes: List[int], sq_err_levels: List[float]) -> float:
    """Fit y = c/x via least squares: minimize ||y - c * (1/x)||_2."""
    xs = [1.0 / max(1, int(r)) for r in sample_sizes if r and r > 0]
    ys = [float(e) for e in sq_err_levels[: len(xs)]]
    if not xs or not ys:
        return 0.0
    # c = (x^T y) / (x^T x)
    num = sum(x * y for x, y in zip(xs, ys))
    den = sum(x * x for x in xs) or 1.0
    return max(0.0, num / den)


def compute_required_rblk(c: float, delta_req: float) -> int:
    """Compute rblk = ceil(c / (delta_req ** 2))."""
    delta_req = max(1e-6, float(delta_req))
    return int(math.ceil(c / (delta_req ** 2)))


def build_histogram_from_samples(samples: List[Any], k: int,
                                 histogram_builder: str = "equi-depth",
                                 data_type: str = None,
                                 ndv: int = None) -> List[Tuple[Any, Any, int]]:
    """Build k-bucket histogram from samples. Returns list of (min_value, max_value, count).
    
    Ensures bucket continuity to match VIDEX's histogram format:
    - Each value should be assignable to exactly one bucket
    - No gaps between bucket boundaries
    - Compatible with MySQL histogram standards
    """

    """
    构建等深直方图
    """
    if not samples:
        return []
    vals = sorted(samples)
    n = len(vals)
    if k <= 0:
        #k = 1
        k = calculate_optimal_buckets(samples, data_type, ndv)
    
    if n < k:
        k = max(1, n)
        print(f"Adjusted buckets from {k} to {max(1, n)} due to small sample size")

    # For equi-depth histogram, each bucket should have roughly n/k elements
    step = max(1, n // k)
    buckets: List[Tuple[Any, Any, int]] = []
    start = 0
    
    for i in range(k):
        if start >= n:
            break
        # Calculate end position for this bucket
        if i == k - 1:  # Last bucket gets all remaining elements
            end = n
        else:
            end = min(n, start + step)
        
        # Create bucket: (min_value, max_value, count)
        bucket_min = vals[start]
        bucket_max = vals[end - 1]
        bucket_count = end - start
        buckets.append((bucket_min, bucket_max, bucket_count))
        
        start = end
    
    # Ensure bucket continuity by adjusting boundaries
    if len(buckets) > 1:
        for i in range(len(buckets) - 1):
            # Make sure the end of bucket i equals the start of bucket i+1
            # This ensures no gaps between buckets
            if buckets[i][1] != buckets[i+1][0]:
                # Adjust the end of current bucket to be the start of next bucket
                buckets[i] = (buckets[i][0], buckets[i+1][0], buckets[i][2])
    
    return buckets


def merge_sorted_samples(a_sorted: List[Any], b_sorted: List[Any]) -> List[Any]:
    """Merge two sorted sample lists."""
    i, j = 0, 0
    out: List[Any] = []
    while i < len(a_sorted) and j < len(b_sorted):
        if a_sorted[i] <= b_sorted[j]:
            out.append(a_sorted[i])
            i += 1
        else:
            out.append(b_sorted[j])
            j += 1
    if i < len(a_sorted):
        out.extend(a_sorted[i:])
    if j < len(b_sorted):
        out.extend(b_sorted[j:])
    return out


def estimate_null_ratio(env: "Env", db: str, table: str, col: str) -> float:
    """Estimate NULL ratio for a column using SQL, consistent with existing logic."""
    total = env.mysql_util.query_for_value(f"SELECT COUNT(1) FROM `{db}`.`{table}`")
    if not total or total <= 0:
        return 0.0
    nulls = env.mysql_util.query_for_value(f"SELECT COUNT(1) FROM `{db}`.`{table}` WHERE `{col}` IS NULL")
    return float(nulls) / float(total)
