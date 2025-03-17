"""
Copyright (c) 2024 Bytedance Ltd. and/or its affiliates
SPDX-License-Identifier: MIT
"""
from typing import List

from sub_platforms.sql_opt.videx.model.videx_model_innodb import VidexModelInnoDB
from sub_platforms.sql_opt.videx.videx_metadata import VidexTableStats
from sub_platforms.sql_opt.videx.model.videx_strategy import VidexStrategy
from sub_platforms.sql_opt.videx.videx_utils import IndexRangeCond


class VidexModelExample(VidexModelInnoDB):
    """
    VidexModelExample estimates NDV, scan_time, and cardinality in a naive way.
    Unlike VidexModelInnoDB, VidexModelExample does not require statistics such as NDV, histograms, or where clauses,
    which can be costly to fetch.

    VidexModelExample inherits from VidexModelInnoDB regarding system variables, schema, and metadata information.
    Fetching this information is efficient since it only requires querying MySQL information tables once.

    The drawback of VidexModelExample is its inaccuracy in characterizing data distribution.
    However, we believe it's a good and simple demonstration for users to get started.

    References:
        MySQL, storage/example/ha_example.cc
    """

    def __init__(self, stats: VidexTableStats, **kwargs):
        super().__init__(stats, **kwargs)
        self.strategy = VidexStrategy.example

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
