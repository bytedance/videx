# -*- coding: utf-8 -*-
"""
Copyright (c) 2024 Bytedance Ltd. and/or its affiliates
SPDX-License-Identifier: MIT

Estimate data_length, avg_row_length, index_length .etc. according to table_rows and table schema (columns typs, index definitions)
"""
import math
import re
from typing import List

from sub_platforms.sql_opt.meta import Table, Column, Index, IndexColumn, IndexType


def estimate_column_length(col_type):
    """
        Estimates the space occupied by a single row of data in a column based on its data type.

        Parameters:
          - col_type: string, e.g., "int", "varchar(255)", "text", etc.

        Returns:
          - An estimated number of bytes.
    """

    col_type = col_type.lower().strip()
    match = re.match(r'([a-z]+)(\((.+?)\))?', col_type)
    if not match:
        return 0
    base = match.group(1)
    params = match.group(3)

    if base in ['int', 'integer']:
        return 4
    elif base == 'bigint':
        return 8
    elif base == 'smallint':
        return 2
    elif base == 'tinyint':
        return 1
    elif base == 'mediumint':
        return 3
    elif base in ['float']:
        return 4
    elif base in ['double']:
        return 8
    elif base == 'decimal':
        return 8
    elif base == 'timestamp':
        return 4
    elif base == 'date':
        return 3
    elif base == 'datetime':
        return 8
    elif base == 'char':
        if params:
            try:
                length = int(params.split(',')[0])
                return length
            except:
                return 1
        return 1
    elif base == 'varchar':
        if params:
            try:
                max_length = int(params.split(',')[0])
                # practical value
                return max_length / 2
            except:
                return 1
        return 1
    elif base in ['text', 'blob']:
        return 100
    else:
        return 50


def estimate_index_key_length(col_type):
    """
    Estimates the length of a column when used as an index key, typically considering only prefix indexes for variable-length fields.

    Parameters:
      - col_type: string, e.g., "int", "varchar(255)", "text", etc.

    Returns:
      - An estimated number of bytes.
    """
    col_type = col_type.lower().strip()
    match = re.match(r'([a-z]+)(\((.+?)\))?', col_type)
    if not match:
        return 0
    base = match.group(1)
    params = match.group(3)

    if base in ['int', 'integer', 'bigint', 'smallint', 'tinyint', 'mediumint',
                'float', 'double', 'decimal', 'timestamp', 'date', 'datetime']:
        return estimate_column_length(col_type)
    elif base in ['char']:
        return estimate_column_length(col_type)
    elif base in ['varchar']:
        if params:
            try:
                max_length = int(params.split(',')[0])
                effective_length = min(max_length, 255)
                return effective_length / 2  # 取平均值
            except:
                return 1
        return 1
    elif base in ['text', 'blob']:
        return 255 / 2
    else:
        return 50


def estimate_total_index_length(table_rows, indexes: List[Index], table_metadata: List[Column]):
    total_estimated_index_length = 0

    # Constants definition
    PRIMARY_KEY_LENGTH = 8  # Assume primary key is bigint, 8 bytes
    INDEX_ENTRY_OVERHEAD = 10  # Fixed overhead for each index record
    FILL_FACTOR_MULTIPLIER = 1.2  # Empirical coefficient for index fill rate
    INDEX_PAGE_SIZE = 16 * 1024  # Index page size 16KB
    PAGE_FILL_RATIO = 0.7  # Page fill factor 70%
    POINTER_SIZE = 6  # Assume pointer size is 6 bytes

    for idx in indexes:
        # Calculate sum of key lengths for columns in the index
        key_length = 0
        for col_name in idx.columns:
            col_name: IndexColumn
            found = False
            for col in table_metadata:
                if col.name.lower() == col_name.name.lower():
                    key_length += estimate_index_key_length(col.column_type)
                    found = True
                    break
            if not found:
                key_length += 50

        # Determine whether to add extra primary key reference based on index type
        if idx.type == IndexType.PRIMARY:
            # Clustered index doesn't need extra primary key reference
            index_record_length = key_length + INDEX_ENTRY_OVERHEAD
        else:
            # Secondary index: record includes primary key reference
            index_record_length = key_length + PRIMARY_KEY_LENGTH + INDEX_ENTRY_OVERHEAD

        # Method 1: Direct estimation
        index_estimation_1 = table_rows * index_record_length * FILL_FACTOR_MULTIPLIER

        # Method 2: Calculation based on index pages and fill factor
        effective_record_size = index_record_length + POINTER_SIZE
        if effective_record_size > 0:
            records_per_page = (INDEX_PAGE_SIZE * PAGE_FILL_RATIO) / effective_record_size
        else:
            records_per_page = table_rows
        num_pages = math.ceil(table_rows / records_per_page) if records_per_page > 0 else 0
        index_estimation_2 = num_pages * INDEX_PAGE_SIZE

        # weighted sum
        weight_1 = 0.5
        index_estimated_size = weight_1 * index_estimation_1 + (1 - weight_1) * index_estimation_2
        total_estimated_index_length += index_estimated_size
        # print(f"estimate index: {idx.db}.{idx.table}.{idx.name}. "
        #       f"by index_record_length: {index_estimation_1} "
        #       f"by fill factor: {index_estimation_2}")
    return total_estimated_index_length


def estimate_data_length(table: Table,
                         fix_row_overhead=10,
                         consider_delete=False, data_free_coefficient=0.1,
                         ):
    """
    Estimates the data_length, index_length, avg_row_length.

    Parameters:
      - table_metadata: Table metadata as a list of dictionaries, each containing at least "name" and "type" fields.
      - table_size: Total table size in bytes (data_length + index_length + [data_free_length]).
      - table_rows: Number of rows in the table (positive integer).
      - indexes: List of indexes on the table, each index is a dictionary that must contain a "columns" key (list of column names).
      - fix_row_overhead: Fixed overhead per row in clustered index (in bytes), default 10 bytes.
      - consider_delete: If True, assumes existence of deleted but unreleased space, to be subtracted from data_length.
      - data_free_coefficient: When consider_delete is True, data_free_length = data_free_coefficient * table_size;
                              default 0.1 (i.e., 10%).

    Returns a dictionary containing the following estimates:
      - avg_row_length: Estimated average length per row (including fix_row_overhead).
      - estimated_data_length_by_rows: Estimate obtained from table_rows * avg_row_length.
      - total_estimated_index_length: Estimated space occupied by all indexes in the table.
      - estimated_data_length_by_table_size: data_length estimate obtained by subtracting index space (and deleted space if applicable) from table_size.
      - combined_estimate: Simple average of the above two methods.
"""
    table_size = table.table_size
    table_rows = table.rows
    columns: List[Column] = table.columns
    indexes: List[Index] = table.indexes
    # 1. Calculate average row length, including estimated values for all columns plus fix_row_overhead (fixed overhead for clustered rows)
    base_row_length = 0

    for col in columns:
        c_len = estimate_column_length(col.column_type)
        # print(f"estimate column: {col.name}, {c_len}")
        base_row_length += c_len
    avg_row_length = base_row_length + fix_row_overhead
    estimated_data_length_by_rows = table_rows * avg_row_length

    # 2. Estimate the size occupied by all indexes
    total_estimated_index_length = estimate_total_index_length(table_rows, indexes, columns)

    # 3. Another estimation method for data_length derived from table_size = data_length + index_length
    # If considering deleted space, then data_free_length = data_free_coefficient * table_size
    data_free_length = data_free_coefficient * table_size if consider_delete else 0
    estimated_data_length_by_table_size = table_size - total_estimated_index_length - data_free_length

    # 4. weighted sum
    # avg_row_length may be very inaccurate due to complex data case, like overflow page.
    # overflow page: for text/blob types, if the line format is COMPACT or DYNAMIC,
    #   it will be stored as an overflow page if it exceeds a certain length.
    weight_row_avg = 0.1
    combined_estimate = (weight_row_avg * estimated_data_length_by_rows
                         + (1 - weight_row_avg) * estimated_data_length_by_table_size)
    assert avg_row_length > 0, f"avg_row_length must be greater than 0, got {avg_row_length}"
    assert total_estimated_index_length > 0, f"total_estimated_index_length must be greater than 0, got {total_estimated_index_length}"
    assert estimated_data_length_by_table_size > 0, f"estimated_data_length_by_table_size must be greater than 0, got {estimated_data_length_by_table_size}"
    assert combined_estimate > 0, f"combined_estimate must be greater than 0, got {combined_estimate}"
    assert data_free_length >= 0, f"data_free_length must be greater than 0, got {data_free_length}"
    return {
        "avg_row_length": avg_row_length,
        "total_estimated_index_length": int(total_estimated_index_length),
        "estimated_data_length_by_rows": int(estimated_data_length_by_rows),
        "estimated_data_length_by_table_size": int(estimated_data_length_by_table_size),
        "combined_estimate": int(combined_estimate),
        "data_free": data_free_length,
    }


if __name__ == "__main__":
    pass
