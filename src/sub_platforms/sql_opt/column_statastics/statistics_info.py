"""
Copyright (c) 2024 Bytedance Ltd. and/or its affiliates
SPDX-License-Identifier: MIT

@ author: bytebrain
@ date: 2025-03-13

"""
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional

from dataclasses_json import DataClassJsonMixin

from sub_platforms.sql_opt.videx.videx_histogram import HistogramStats


@dataclass
class TableStatisticsInfo(DataClassJsonMixin):
    db_name: str
    table_name: str
    # {col_name: col ndv}
    ndv_dict: Optional[Dict[str, float]] = field(default_factory=dict)
    # {col_name: histogram}
    histogram_dict: Optional[Dict[str, HistogramStats]] = field(default_factory=dict)
    # {col_name: not null ratio}
    not_null_ratio_dict:  Optional[Dict[str, float]] = field(default_factory=dict)

    # 表总行数
    num_of_rows: Optional[int] = field(default=0)
    max_pk: Optional[Any] = field(default=None)
    min_pk: Optional[Any] = field(default=None)

    # sample related info
    is_sample_success: Optional[bool] = field(default=True)
    is_sample_supported: Optional[bool] = field(default=True)
    unsupported_reason: Optional[str] = field(default=None)
    sample_rows: Optional[int] = field(default=0)
    local_path_prefix: Optional[str] = field(default=None)
    tos_path_prefix: Optional[str] = field(default=None)
    sample_file_list: Optional[List[str]] = field(default_factory=list)
    block_size_list: Optional[List[int]] = field(default_factory=list)
    shard_no: Optional[int] = field(default=0)
    # {col_name: sample error}
    sample_error_dict: Optional[Dict[str, str]] = field(default_factory=dict)
    # {col_name: histogram error}
    histogram_error_dict: Optional[Dict[str, float]] = field(default_factory=dict)
    msg: Optional[str] = None
    extra_info: Optional[Dict[str, Any]] = field(default_factory=dict)

    _version: Optional[str] = field(default='1.0.0')


def trans_dict_to_statistics(numerical_info: Dict[str, Any]) -> TableStatisticsInfo:
    """a temp convert function，from numerical info to TableStatisticsInfo"""
    table_statistics = TableStatisticsInfo()
    table_statistics.ndv_dict = numerical_info['ndv_dict']
    table_statistics.histogram_dict = numerical_info['histogram']
    table_statistics.not_null_ratio_dict = numerical_info['not_null_ratio_dict']
    table_statistics.num_of_rows = numerical_info['num_of_rows']
    table_statistics.is_sample_success = numerical_info['is_sample_succ']
    table_statistics.shard_no = numerical_info['shard_no']
    return table_statistics
    
    