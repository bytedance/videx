"""
Copyright (c) 2024 Bytedance Ltd. and/or its affiliates
SPDX-License-Identifier: MIT
"""

import json
import logging
import time
import traceback
from typing import List

import numpy as np
from cachetools import TTLCache

from sub_platforms.sql_opt.histogram.ndv_estimator import NDVEstimator
from sub_platforms.sql_opt.histogram.histogram_utils import load_sample_file
from sub_platforms.sql_opt.videx.videx_histogram import MEANINGLESS_INT
from sub_platforms.sql_opt.videx.videx_metadata import VidexTableStats, PCT_CACHED_MODE_PREFER_META
from sub_platforms.sql_opt.videx.model.videx_strategy import VidexModelBase, VidexStrategy, calc_mulcol_ndv_independent
from sub_platforms.sql_opt.videx.videx_utils import IndexRangeCond, RangeCond


class VidexModelInnoDB(VidexModelBase):
    """
    The `Model` contains table-level information, including `stats` and other details specific within a table.
    """

    def __init__(self, stats: VidexTableStats, **kwargs):
        super().__init__(stats, VidexStrategy.innodb)
        # for multi col range query, if the first column is not equal, btree will ignore the rest.
        # refer to append_range_all_keyparts::keypart_range
        # /*
        #   Print range predicates for consecutive keyparts if
        #   1) There are predicates for later keyparts, and
        #   2) We explicitly requested to print even the ranges that will
        #      not be usable by range access, or
        #   3) There are no "holes" in the used keyparts (keypartX can only
        #      be used if there is a range predicate on keypartX-1), and
        #   4) The current range is an equality range
        # */
        self.ignore_range_after_neq: bool = True
        # if not PCT_CACHED_MODE_PREFER_META, pct_cached will be forcibly set to the given pct
        self.pct_cached: float = kwargs.get('pct_cached', PCT_CACHED_MODE_PREFER_META)
        # ndv is usually stable and calculation is costly, thus we cache it in task-level.
        # key: table, fields list
        self.ndv_cache = TTLCache(maxsize=1000, ttl=1200)
        self.ndv_model = None
        self.df_sample_raw = None
        self.loading_ndv_model()
        self.inject_cardinality_dict = dict()
        # self.inject_cardinality_dict["C_NATIONKEY = 15"] = 58
        # self.inject_cardinality_dict["'1995-01-01' <= O_ORDERDATE <= '1996-12-31'"] = 4509

    def loading_ndv_model(self):
        if self.table_stats and self.table_stats.sample_file_info is not None:
            logging.info(f"loading ndv model: NDVEstimator, table_name={self.table_name}")
            st = time.perf_counter()
            table_rows = self.table_stats.records
            self.ndv_model = NDVEstimator(table_rows)
            self.df_sample_raw = load_sample_file(self.table_stats)
            logging.info(f"loading ndv model: NDVEstimator, table_name={self.table_name}, "
                         f"use {time.perf_counter() - st:.2f} seconds")

    def scan_time(self, req_json_item: dict) -> float:
        return self.table_stats.clustered_index_size
        # raise NotImplementedError(
        #     "This scan_time is not implemented in VidexModelInnoDB. how to get self.stats.clustered_index_size?")

    def get_memory_buffer_size(self, req_json_item: dict) -> int:
        return self.table_stats.innodb_buffer_pool_size

    def cardinality(self, idx_range_cond: IndexRangeCond) -> int:
        condition_str = idx_range_cond.ranges_to_str()
        if condition_str in self.inject_cardinality_dict:
            return self.inject_cardinality_dict[condition_str]

        debug_msg = f"{idx_range_cond=}," \
                    f"idx_gt_pair_dict={json.dumps(self.table_stats.gt_return.idx_gt_pair_dict)}"
        try:
            gt = self.table_stats.gt_return.find(idx_range_cond, self.ignore_range_after_neq)
            if gt is not None:
                # find existed key
                logging.warning(f"TRY to use GT records_in_range. {debug_msg} found {gt=} ")
                return gt
            else:
                # print input for debug
                logging.warning(f"TRY to use GT records_in_range but NOGT. {gt=}")
        except Exception as e:
            logging.error(f"DEBUG NOGT:    {debug_msg}\n Meet error: {e} {traceback.format_exc()}")


        ranges = idx_range_cond.get_valid_ranges(self.ignore_range_after_neq)
        min_freqs, max_freqs = [0] * len(ranges), [1] * len(ranges)
        for c, rc in enumerate(ranges):
            rc: RangeCond
            col_hist = self.table_stats.get_col_hist(rc.col)
            if col_hist is None or len(col_hist.buckets) == 0:
                # If a column ndv is missing, we tend to overestimate its cost
                logging.warning(f"require cardinality for {rc.col} but no hist found. ignore it.")
                min_freqs[c], max_freqs[c] = 0, 1
                continue

            # for multi-column, the first few columns cannot be processed as the usual manner.
            # Refer to the parsing method of `range_cond`.
            if rc.has_min():
                # TODO Handle the case for NULL < c.
                #  In MySQL conditions, NULL is represented as the string 'NULL',
                #  and the string 'NULL' is represented as "'NULL'".
                min_freqs[c] = col_hist.find_nearest_key_pos(rc.min_value, rc.min_key_pos_side)
            if rc.has_max():
                max_freqs[c] = col_hist.find_nearest_key_pos(rc.max_value, rc.max_key_pos_side)
            if min_freqs[c] > max_freqs[c]:
                if abs(min_freqs[c] - max_freqs[c]) / max(min_freqs[c], max_freqs[c]) < 0.01:
                    # both min and max are non-zero and very closed, may be an estimation error
                    logging.warning(f"invalid range: {self.table_name}.{rc.col} {rc} min={min_freqs[c]} max={max_freqs[c]}")
                    min_freqs[c], max_freqs[c] = max_freqs[c], min_freqs[c]
                else:
                    raise Exception(f"invalid range: {self.table_name}.{rc.col} {rc} min={min_freqs[c]} max={max_freqs[c]}")
            logging.info(f"card_range_cond ({self.table_name}({self.table_stats.records}), {idx_range_cond.index_name}) "
                         f"[{c}/{len(ranges)}]: {rc} selectivity={max_freqs[c]-min_freqs[c]:.3%}, "
                         f"after_rows={int(self.table_stats.records * np.prod(np.array(max_freqs[:c+1]) - np.array(min_freqs[:c+1])))} "
                         f"freq: [{min_freqs[c]:.4f}, {max_freqs[c]:.4f}], ")
        records_in_ranges = int(self.table_stats.records * np.prod(np.array(max_freqs) - np.array(min_freqs)))
        if records_in_ranges == 0:
            # refer to innodb.cc
            # The MySQL optimizer seems to believe an estimate of 0 rows is always accurate and may return
            # the result 'Empty set' based on that. The accuracy is not guaranteed, and even if it were,
            # for a locking read we should anyway perform the search to set the next-key lock.
            # Add 1 to the value to make sure MySQL does not make the assumption!
            logging.warning(f"records_in_ranges is 0, set to 1")
            records_in_ranges = 1

        return records_in_ranges

    def ndv(self, index_name, field_list: List[str]) -> int:
        ndv = self.table_stats.get_ideal_ndv(index_name, field_list)
        if ndv is None:
            if self.table_stats.sample_file_info is not None:
                table_rows = self.table_stats.records
                # table_ndv_estimator = NDVEstimator(table_rows)
                st = time.perf_counter()
                ndv = self.ndv_model.estimate_multi_columns(self.df_sample_raw, field_list, table_rows)
                # ndv = table_ndv_estimator.estimate_multi_columns(df_sample_raw, field_list)
                elapsed_time = time.perf_counter() - st
                logging.info(f"ndv calculate: {ndv=} {elapsed_time=:.2f}s")
            else:
                ndv = calc_mulcol_ndv_independent(field_list, self.table_stats.ndvs_single,
                                                  self.table_stats.records)
        return ndv

    def info_low(self, req_json_item: dict) -> dict:
        """
        virtual ull info();

        return the following data:
        - stat_n_rows
        - stat_clustered_index_size
        - stat_sum_of_other_index_sizes
        - data_file_length
        - index_file_length
        - data_free_length：used to calculated deleted_length
        - key->name #@# key->key_part[j].field->field_name
            - rec_per_key: table_rows / ndv
            - srv_innodb_stats_method，or set to default
        """
        CONCAT = " #@# "
        res = {
            "stat_n_rows": self.table_stats.records,
            "stat_clustered_index_size": self.table_stats.clustered_index_size,
            # TODO `stat_sum_of_other_index_sizes` may change
            "stat_sum_of_other_index_sizes": self.table_stats.sum_of_other_index_sizes,
            "data_file_length": self.table_stats.data_file_length,
            "index_file_length": self.table_stats.index_file_length,
            "data_free_length": self.table_stats.data_free_length,
            "innodb_buffer_pool_size": self.table_stats.innodb_buffer_pool_size,

        }
        for i, key_json in enumerate(req_json_item['data']):
            assert key_json['item_type'] == 'key'
            key_length = key_json['properties']['key_length']
            key_name = key_json['properties']['name']

            # load pct_cached
            # TODO Based on preliminary experiments, pct_cached significantly influences index selection.
            #  We should adopt the configuration most inclined to use indexes,
            #  especially for TPCE 6b49df9400c7d1840df47168761e0831.

            # index_pct_cached = 1
            # if key_name == 'PRIMARY':
            #     index_pct_cached = 1
            # else:
            #     index_pct_cached = 1
            # 0 may be a good choice, indicating that no index data is loaded into memory.
            DEFAULT_PCT = 0
            if self.pct_cached == PCT_CACHED_MODE_PREFER_META:
                index_pct_cached = self.table_stats.pct_cached.get(key_name, {}).get('pct_cached', 0)
            elif 0 <= self.pct_cached <= 1:
                index_pct_cached = self.pct_cached
            else:
                index_pct_cached = DEFAULT_PCT

            res["pct_cached" + CONCAT + key_name] = index_pct_cached

            first_fields = []
            for j, field_json in enumerate(key_json['data']):
                # The flags for i and j are consistent with InnoDB.
                assert field_json['item_type'] == 'field'
                field_name = field_json['properties']['name']
                store_length = field_json['properties']['store_length']
                first_fields.append(field_name)
                ndv_key = (key_name, tuple(first_fields))
                if ndv_key in self.ndv_cache:
                    ndv = self.ndv_cache[ndv_key]
                    logging.info(f"load existing ndv from cache: table={self.table_name} NDV({ndv_key}) = {ndv}")
                else:
                    st = time.perf_counter()
                    ndv = self.ndv(key_name, first_fields)
                    self.ndv_cache[ndv_key] = ndv
                    logging.info(f"calculate ndv and save to cache: table={self.table_name}: NDV({ndv_key}) = {ndv} "
                                 f"use {time.perf_counter() - st:.2f}s")

                def _help(n_diff, records) -> float:
                    """
                    mock the function
                    rec_per_key_t innodb_rec_per_key(const dict_index_t *index, ulint i,
                                 ha_rows records);
                    Args:
                        n_diff: n_diff
                        records: 总行数

                    Returns:
                        rec_per_key
                    """
                    if records == 0:
                        return 1.0
                    if n_diff is None or n_diff == 0 or n_diff < 0:
                        rec_per_key = records
                    else:
                        # TODO Handle the null value scenario,
                        #  i.e. else if (srv_innodb_stats_method == SRV_STATS_NULLS_IGNORED)
                        rec_per_key = records / n_diff
                    if rec_per_key < 1.0:
                        # Values below 1.0 are meaningless and must be due to the stats being imprecise.
                        rec_per_key = 1.0

                    if rec_per_key is None:
                        logging.warning(
                            f"get ndv None for {self.table_stats.table_name}, {key_name}, {field_name}, set 1")
                        rec_per_key = 1.0
                    return rec_per_key

                concat_key = "rec_per_key" + CONCAT + key_name + CONCAT + field_name
                res[concat_key] = _help(ndv, self.table_stats.records)

        return res
