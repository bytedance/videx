"""
Copyright (c) 2024 Bytedance Ltd. and/or its affiliates
SPDX-License-Identifier: MIT
"""
from typing import Dict, List, Any, Optional
from pydantic import Field, PrivateAttr, PlainSerializer, BeforeValidator
from typing_extensions import Annotated
from pandas import pd

from sub_platforms.sql_opt.videx.videx_histogram import HistogramStats
from sub_platforms.sql_opt.column_statastics.statistics_info_base import BaseTableStatisticsInfo

def large_number_decoder(y):
    if isinstance(y, list):
        for item in y:
            if isinstance(item, dict) and "Value" in item:
                item['Value'] = str(item['Value'])
        return y
    else:
        res = [{"ColumnName": "id", "Value": str(y)}]
        return res


class TableStatisticsInfo(BaseTableStatisticsInfo):
    db_name: str
    table_name: str
    # {col_name: col ndv}
    ndv_dict: Optional[Dict[str, float]] = Field(default_factory=dict)
    # {col_name: histogram}
    histogram_dict: Optional[Dict[str, HistogramStats]] = Field(default_factory=dict)
    # {col_name: not null ratio}
    not_null_ratio_dict:  Optional[Dict[str, float]] = Field(default_factory=dict)

    # table rows
    num_of_rows: Optional[int] = Field(default=0)
    max_pk: Annotated[Optional[List[Dict[str, str]]], BeforeValidator(large_number_decoder)] = Field(default=None)
    min_pk: Annotated[Optional[List[Dict[str, str]]], BeforeValidator(large_number_decoder)] = Field(default=None)

    # sample related info
    is_sample_success: Optional[bool] = Field(default=True)
    is_sample_supported: Optional[bool] = Field(default=True)
    unsupported_reason: Optional[str] = Field(default=None)
    sample_rows: Optional[int] = Field(default=0)
    local_path_prefix: Optional[str] = Field(default=None)
    tos_path_prefix: Optional[str] = Field(default=None)
    sample_file_list: Optional[List[str]] = Field(default_factory=list)
    block_size_list: Optional[List[int]] = Field(default_factory=list)
    shard_no: Optional[int] = Field(default=0)
    # {col_name: sample error}
    sample_error_dict: Optional[Dict[str, str]] = Field(default_factory=dict)
    # {col_name: histogram error}
    histogram_error_dict: Optional[Dict[str, float]] = Field(default_factory=dict)
    msg: Optional[str] = None
    extra_info: Optional[Dict[str, Any]] = Field(default_factory=dict)
    sample_data: Optional[pd.DataFrame] = Field(default=None, exclude=True)

    _version: Optional[str] = PrivateAttr(default='1.0.0')


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
    
    