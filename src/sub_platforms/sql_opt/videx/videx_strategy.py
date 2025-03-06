# -*- coding: utf-8 -*-
"""
TODO: add file description.

@ author: kangrong
@ date: 2023/11/8 
"""
import enum
import json
import logging
import traceback
from abc import abstractmethod, ABC
from typing import List, Dict

import numpy as np

from sub_platforms.sql_opt.histogram.histogram_utils import NDVEstimator, load_sample_file
from sub_platforms.sql_opt.videx.videx_metadata import VidexTableStats
from sub_platforms.sql_opt.videx.videx_utils import str_lower_eq, IndexRangeCond, RangeCond


class VidexStrategy(enum.Enum):
    example = "default"  # 采用 MySQL example （部分自实现，部分继承自 handler）方案。特点是仅基于 stats，不基于其他信息
    innodb = "innodb"  # 结合 stats + innodb schema metadata，尽量贴合
    ideal = "ideal"  # 上帝视角，知晓很难得到的统计细节，目的是查询漏洞：如果不能完美 hack innodb，说明有其他 phase 没考虑到


class VidexModelBase(ABC):
    """
    Abstract cost model class. VIDEX-Statistic-Server receives requests from VIDEX-MySQL for Cardinality
    and NDV estimates, parses them into structured data for ease use of developers.

    Implement these methods to inject Cardinality and NDV algorithms into MySQL.
    """
    def __init__(self, stats: VidexTableStats, strategy: VidexStrategy):
        self.table_stats: VidexTableStats = stats
        self.strategy: VidexStrategy = strategy

    @abstractmethod
    def cardinality(self, idx_range_cond: IndexRangeCond) -> int:
        """
        Estimates the cardinality (number of rows matching a criteria) for a given index range condition.

        Parameters:
        idx_range_cond (IndexRangeCond): Condition object representing the index range.

        Returns:
        int: Estimated number of rows that match the condition.

        Example:
        where c1 = 3 and c2 < 3 and c2 > 1, ranges = [RangeCond(c1 = 3), RangeCond(c2 < 3 and c2 > 1)]
        """
        pass

    @abstractmethod
    def ndv(self, index_name: str, field_list: List[str]) -> int:
        """
        Estimates the number of distinct values (NDV) for specified fields within an index.

        Parameters:
        index_name (str): Name of the index.
        field_list (List[str]): List of fields for which NDV is to be estimated.

        Returns:
        int: Estimated number of distinct values.

        Example:
        index_name = 'idx_c1c2', field_list = ['c1', 'c2']
        """
        raise NotImplementedError()

    @abstractmethod
    def scan_time(self, req_json_item: dict) -> float:
        """
        virtual double scan_time();
        """
        raise NotImplementedError()

    @abstractmethod
    def get_memory_buffer_size(self, req_json_item: dict) -> int:
        """
        virtual double get_memory_buffer_size();
        """
        raise NotImplementedError()

    @abstractmethod
    def info_low(self, req_json_item: dict) -> int:
        """
        virtual ull info();
        """
        raise NotImplementedError()

    def records_in_range(self, req_json_item: dict) -> int:
        """
        virtual ull records_in_range();
        """
        # parse key
        # assert str_lower_eq(req_json_item.get('properties').get('dbname'), self.stats.dbname)
        assert str_lower_eq(req_json_item.get('properties').get('table_name'), self.table_stats.table_name)
        assert len(req_json_item['data']) == 2
        min_key = req_json_item['data'][0]
        max_key = req_json_item['data'][1]
        assert min_key['item_type'] == 'min_key'
        assert max_key['item_type'] == 'max_key'

        idx_range_cond = IndexRangeCond.from_dict(min_key, max_key)

        """
        有 key 的格式如下：
        {
            "item_type": "min_key",
            "properties": {
                "index_name": "idx_S_DIST_10",
                "length": "24",
                "operator": ">"
            },
            "data": [
                {
                  'item_type': 'column_and_bound',
                  'properties': {
                    'column': 'S_YTD',
                    'value': '123.00'
                  },
                  'data': []
                },
                {
                  'item_type': 'column_and_bound',
                  'properties': {
                    'column': 'S_DIST_10',
                    'value': "'123'"
                  },
                  'data': []
                }
          ]
        }
        NO_KEY_RANGE 的格式是下面这样：
            {
            "item_type": "max_key",
            "properties": {},
            "data": []
            }
        """
        return self.cardinality(idx_range_cond)


class VidexModelExample(VidexModelBase):
    """
    example 原本的策略
    """
    def __init__(self, stats: VidexTableStats,  **kwargs):
        super().__init__(stats, VidexStrategy.example)

    def scan_time(self, req_json_item: dict) -> float:
        return (self.table_stats.records + self.table_stats.deleted) / 20.0 + 10

    def get_memory_buffer_size(self, req_json_item: dict) -> int:
        return -1

    def cardinality(self, idx_range_cond: IndexRangeCond) -> int:
        """
        corresponds to cardinality methods
        """
        return 10

    def ndv(self, index_name, field_list: List[str]) -> int:
        return 1

    def info_low(self, req_json_item: dict) -> int:
        """
        virtual ull info();
        """
        raise NotImplementedError()


def record_range_request_to_str(min_key: dict, max_key: dict) -> str:
    """
    min_key 和 max_key 来自于 mysql 底层函数调用。将他们转化为标准格式的表达式：col OP val，用于和 trace 作比较
    Args:
        min_key:
        max_key:

    Returns:

    """
    return ""


def calc_mulcol_ndv_independent(col_names: List[str], ndvs_single: Dict[str, int], table_rows: int) -> int:
    """
    基于多列ndv 独立分布假设，根据单列 ndv 计算出 n 列的 ndv
    Args:
        col_names: column name list
        ndvs_single: col_name -> ndv
        table_rows: 总行数

    Returns:

    """

    # 计算所有列NDV的乘积

    ndv_product = 1
    for col in col_names:
        if col in ndvs_single:
            ndv_product *= ndvs_single[col]
        else:
            raise ValueError(f"Column {col} not found in ndvs_single when calc_mulcol_ndv_independent")

    # 联合NDV不可能超过表的总行数
    return min(ndv_product, table_rows)


class VidexModelInnoDB(VidexModelBase):
    """
    Model是 table-level 的信息，内部包含的 stats 等等都是针对于一个表的
    """

    def __init__(self, stats: VidexTableStats,  **kwargs):
        super().__init__(stats, VidexStrategy.innodb)
        # btree 多列查询时，如果第一列不是等值，会忽略后续
        # 参考 append_range_all_keyparts::keypart_range
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

    def scan_time(self, req_json_item: dict) -> float:
        return self.table_stats.clustered_index_size
        # raise NotImplementedError(
        #     "This scan_time is not implemented in VidexModelInnoDB. how to get self.stats.clustered_index_size?")

    def get_memory_buffer_size(self, req_json_item: dict) -> int:
        return self.table_stats.innodb_buffer_pool_size

    def cardinality(self, idx_range_cond: IndexRangeCond) -> int:
        debug_msg = f"{idx_range_cond=}," \
                    f"idx_gt_pair_dict={json.dumps(self.table_stats.gt_return.idx_gt_pair_dict)}"
        try:
            gt = self.table_stats.gt_return.find(idx_range_cond, self.ignore_range_after_neq)
            if gt is not None:
                # 寻找已有的 key
                logging.warning(f"TRY to use GT records_in_range. {debug_msg} found {gt=} ")
                return gt
            else:
                # print input for debug
                logging.warning(f"TRY to use GT records_in_range but NOGT. {gt=}")
        except Exception as e:
            logging.error(f"DEBUG NOGT:    {debug_msg}\n Meet error: {e} {traceback.format_exc()}")

        # 假如 min_key 有 2 列，分别 cum_freq 是 0.1，0.6；max_key 有一列条件，分别是 0.3, 1 则 records = (0.3-0.1) * (1-0.6)
        ranges = idx_range_cond.get_valid_ranges(self.ignore_range_after_neq)
        min_freqs, max_freqs = [0] * len(ranges), [1] * len(ranges)
        for c, rc in enumerate(ranges):
            rc: RangeCond
            col_hist = self.table_stats.get_col_hist(rc.col)
            # 多列情况下，前几列不能按照正常方式处理，参考 range_cond 的 parse 方式
            if rc.has_min():
                min_freqs[c] = col_hist.find_nearest_key_pos(rc.min_value, rc.min_key_pos_side)
            if rc.has_max():
                max_freqs[c] = col_hist.find_nearest_key_pos(rc.max_value, rc.max_key_pos_side)

        records_in_ranges = int(self.table_stats.records * np.prod(np.array(max_freqs) - np.array(min_freqs)))
        if records_in_ranges == 0:
            # refer to innodb.cc
            # The MySQL optimizer seems to believe an estimate of 0 rows is always accurate and may return
            # the result 'Empty set' based on that. The accuracy is not guaranteed, and even if it were,
            # for a locking read we should anyway perform the search to set the next-key lock.
            # Add 1 to the value to make sure MySQL does not make the assumption!
            records_in_ranges = 1

        return records_in_ranges

    def ndv(self, index_name, field_list: List[str]) -> int:
        ndv = self.table_stats.get_ideal_ndv(index_name, field_list)
        if ndv is None:
            if self.table_stats.sample_file_info is not None:
                table_rows = self.table_stats.records
                table_ndv_estimator = NDVEstimator(table_rows)
                df_sample_raw = load_sample_file(self.table_stats)
                ndv = table_ndv_estimator.estiamte_multi_columns(df_sample_raw, field_list)
            else:
                ndv = calc_mulcol_ndv_independent(field_list, self.table_stats.ndvs_single,
                                                  self.table_stats.records)
        return ndv

    def info_low(self, req_json_item: dict) -> dict:
        """
        virtual ull info();

        需要返回如下内容：
        - stat_n_rows
        - stat_clustered_index_size
        - stat_sum_of_other_index_sizes
        - data_file_length
        - index_file_length
        - data_free_length：用于计算 deleted_length
        - key->name #@# key->key_part[j].field->field_name
            - rec_per_key 在 python 直接算好
            - srv_innodb_stats_method，或者取默认
        """
        CONCAT = " #@# "
        res = {
            "stat_n_rows": self.table_stats.records,
            "stat_clustered_index_size": self.table_stats.clustered_index_size,
            # TODO stat_sum_of_other_index_sizes 这个可能会有变化
            "stat_sum_of_other_index_sizes": self.table_stats.sum_of_other_index_sizes,
            "data_file_length": self.table_stats.data_file_length,
            "index_file_length": self.table_stats.index_file_length,
            "data_free_length": self.table_stats.data_free_length,

        }
        for i, key_json in enumerate(req_json_item['data']):
            assert key_json['item_type'] == 'key'
            key_length = key_json['properties']['key_length']
            key_name = key_json['properties']['name']

            # load pct_cached
            # 加载 index pct cached
            # TODO 根据不完全实验，pct_cached 将比较明显的影响索引的选择。我们应该找出最倾向于使用索引的配置
            #  特别是 TPCE 6b49df9400c7d1840df47168761e0831。可以作为下一步研究方向
            # if key_name in self.table_stats.pct_cached:
            #     index_pct_cached = self.table_stats.pct_cached[key_name]['pct_cached']
            # else:
            #     index_pct_cached = 1
            # 默认为 0，也即无加载到内存，也许是个不错的选择
            # if key_name == 'PRIMARY':
            #     index_pct_cached = 1
            # else:
            #     index_pct_cached = 1
            index_pct_cached = 1
            res["pct_cached" + CONCAT + key_name] = index_pct_cached

            first_fields = []
            for j, field_json in enumerate(key_json['data']):
                # i, j 的标志位和 innodb 是一致的
                assert field_json['item_type'] == 'field'
                field_name = field_json['properties']['name']
                store_length = field_json['properties']['store_length']
                first_fields.append(field_name)
                # 返回 rec_per_key
                ndv = self.ndv(key_name, first_fields)
                # first_fields = [c.lower() for c in first_fields]
                # if self.use_gt:
                #     logging.warning(f"TRY to use GT info_low")

                # 新版本中，不再通过 use_gt 来区分，而是通过是否传入了 multi_ndv、或者其他 gt 信息来区分。如果有传入 gt，就用 gt


                def _help(n_diff, records) -> float:
                    """
                    模拟
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
                        # TODO 未处理空值情况，也即 else if (srv_innodb_stats_method == SRV_STATS_NULLS_IGNORED)
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


if __name__ == '__main__':
    pass
