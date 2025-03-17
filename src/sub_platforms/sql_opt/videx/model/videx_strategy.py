# -*- coding: utf-8 -*-
"""
Copyright (c) 2024 Bytedance Ltd. and/or its affiliates
SPDX-License-Identifier: MIT
"""
import enum
import logging
from abc import abstractmethod, ABC
from typing import List, Dict

from sub_platforms.sql_opt.videx.videx_metadata import VidexTableStats
from sub_platforms.sql_opt.videx.videx_utils import str_lower_eq, IndexRangeCond


class VidexStrategy(enum.Enum):
    # Refer to MySQL example engine. It relies solely on MySQL system statistics, calculate cost in a simple way.
    example = "example"
    # Utilize both MySQL system statistics with InnoDB statistics
    innodb = "innodb"
    # A god's-eye view, aware of hard-to-obtain statistical details.
    # This type is for debugging: if InnoDB can't be perfectly mocked, it indicates that we miss some logic.
    ideal = "ideal"
    # sqlbrain
    sqlbrain = "sqlbrain"


class VidexModelBase(ABC):
    """
    Abstract cost model class. VIDEX-Statistic-Server receives requests from VIDEX-MySQL for Cardinality
    and NDV estimates, parses them into structured data for ease use of developers.

    Implement these methods to inject Cardinality and NDV algorithms into MySQL.
    """
    def __init__(self, stats: VidexTableStats, strategy: VidexStrategy):
        self.table_stats: VidexTableStats = stats
        self.strategy: VidexStrategy = strategy

    @property
    def table_name(self):
        return self.table_stats.table_name

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


def record_range_request_to_str(min_key: dict, max_key: dict) -> str:
    """
    `min_key` and `max_key` are derived from underlying MySQL function calls.
    Convert them into the standard format expression: `col OP val`, for comparison with trace data.
    Args:
        min_key:
        max_key:

    Returns:

    """
    return ""


def calc_mulcol_ndv_independent(col_names: List[str], ndvs_single: Dict[str, int], table_rows: int) -> int:
    """
    Based on the assumption of independent distribution across multiple column NDVs,
    calculate the NDV for multiple columns from the single column NDV.

    Args:
        col_names: column name list
        ndvs_single: col_name -> ndv
        table_rows

    Returns:

    """

    ndv_product = 1
    for col in col_names:
        if col in ndvs_single:
            ndv_product *= ndvs_single[col]
        else:
            logging.warning(f"Column {col} not found in ndvs_single when calc_mulcol_ndv_independent")
            # If a column ndv is missing, we tend to overestimate its cost, implying `ndv(col) as 1`, and `cardinality as table_rows`.
            ndv_product *= 1

    # The combined NDV cannot exceed the total number of rows in the table.
    return min(ndv_product, table_rows)


if __name__ == '__main__':
    pass
