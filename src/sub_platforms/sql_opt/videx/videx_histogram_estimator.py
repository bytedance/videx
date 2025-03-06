import math
from typing import Any, Dict, List

import pandas as pd

from sub_platforms.sql_opt.histogram.histogram_utils import get_column_data_type
from sub_platforms.sql_opt.videx.videx_histogram import convert_str_by_type


class HistogramEstimator:
    """
    基于采样的结果构建histogram，对一个表实例化一次，和Sampler一样
    """
    def __init__(self, sample_data: pd.DataFrame, numerical_info, table_meta, bucket_len: int = 10) -> None:
        self.sample_data = sample_data 
        self.numerical_info = numerical_info
        self.bucket_len = bucket_len
        self.table_meta = table_meta
        self.init_scale_factor()
    
    def _compute_column_scale_factor(self, column):
        estimated_ndv = self.numerical_info['ndv_dict'][column]
        sample_ndv = self.sample_data[column].nunique()
        scale_factor = estimated_ndv / sample_ndv
        return scale_factor
    
    def init_scale_factor(self) -> None:
        column_names = self.sample_data.columns.to_list()
        scale_dict = {}
        for column_name in column_names:
            scale_dict[column_name] = self._compute_column_scale_factor(column_name)
        self.scale_dict = scale_dict
    
    def _get_short_buckets(self, column_name, data_type) -> List[Dict[str, Any]]:
        # 对于长度小于 bucket_len 的数据，每个值都是一个bucket
        column_data = self.sample_data[column_name].dropna()
        data_len = len(column_data)
        bucket_list = []
        column_sorted = column_data.sort_values().reset_index(drop=True)
        for i in range(data_len):
            bucket_list.append(
                {
                'min_value': convert_str_by_type(column_sorted[i], data_type=data_type),
                'max_value': convert_str_by_type(column_sorted[i], data_type=data_type),
                'cum_freq': (i + 1) / len(column_sorted),
                'row_count': 1,
                }
            )

        return bucket_list
    
    def _get_long_buckets(self, column_name, data_type) -> List[Dict[str, Any]]:
        # 长度 >= bucket_len，需要划分每个 bucket 里需要分配多少个值
        column_data = self.sample_data[column_name].dropna()
        if data_type == 'date':
            column_data = column_data[column_data != '0000-00-00 00:00:00']
        bucket_list = []
        # 每个bucket里的值需要向上取整，让最后一个bucket的值最少
        nums_per_bucket = int(math.ceil(len(column_data) / self.bucket_len))
        column_sorted = column_data.sort_values().reset_index(drop=True)
        cum_freq = 0
        for i in range(self.bucket_len):
            lower_bound = i * nums_per_bucket
            # 如果下界长度超长，例如len=25, bucket_len = 10 时，提前跳出
            if lower_bound >= len(column_data):
                continue
            upper_bound = min(len(column_data), (i + 1) * nums_per_bucket) - 1
            cum_freq += (upper_bound - lower_bound + 1) / len(column_sorted)
            bucket_list.append(
                {
                'min_value': convert_str_by_type(column_sorted[lower_bound], data_type=data_type),
                'max_value': convert_str_by_type(column_sorted[upper_bound], data_type=data_type),
                'cum_freq': cum_freq,
                'row_count': int(column_sorted[lower_bound: upper_bound].nunique() * self.scale_dict[column_name])
                }
            )
        return bucket_list
    
    def _get_column_data_type(self, column_name: str) -> str:
        data_type = 'str'
        column_type = None
        for column in self.table_meta.columns:
            if column.name == column_name:
                column_type = column.data_type
        if column_type is None:
            raise ValueError(f"column {column_name} not found in {self.table_meta.columns}")
        data_type = get_column_data_type(data_type)
        return data_type
    def get_column_histogram(self, column_name: str) -> List[Dict[str, Any]]:
        """
        根据采样结果，构建列的histogram
        """
        column_data = self.sample_data[column_name].dropna()
        bucket_list = []
        if len(column_data) == 0:
            return bucket_list
        
        data_type = self._get_column_data_type(column_name)
        
        if len(column_data) < self.bucket_len:
            bucket_list = self._get_short_buckets(column_name, data_type)
        else:
            bucket_list = self._get_long_buckets(column_name, data_type)
        return bucket_list
    
    def get_histogram_from_samples(self) -> Dict:
        # df 是采样的表的数据，从 Sampler 里可以拿到，返回这个表的histogram {column_name: bucket list}
        column_names = self.sample_data.columns.to_list()
        histogram_dict = {}
        for column_name in column_names:
            histogram_dict[column_name] = {}
            histogram_dict[column_name]['buckets'] = self.get_column_histogram(column_name)
            histogram_dict[column_name]['data_type'] = self._get_column_data_type(column_name)
            histogram_dict[column_name]['histogram_type'] = 'equi-height'
        return histogram_dict
    
    def get_histogram(self) -> Dict:
        # 从采样数据中计算 histogram
        # 根据采样率，估算的 NDV，实际的 NDV 等信息估计原表数据的 histogram
        histogram_dict = self.get_histogram_from_samples()
        return histogram_dict
