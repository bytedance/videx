import logging
import os

import pandas as pd
import math
import numpy as np
from typing import Any, Dict, List
from pandas import DataFrame
from collections import Counter

from sub_platforms.sql_opt.videx.videx_histogram import HistogramBucket, HistogramStats, convert_str_by_type
from sub_platforms.sql_opt.videx.videx_metadata import VidexTableStats
from estndv import ndvEstimator


def get_column_data_type(column_type: str):
    """
    convert mysql data type to inner type
    """
    data_type = None
    if 'int' in column_type:
        data_type = 'int'
    elif column_type == 'float':
        data_type = 'float'
    elif column_type == 'double':
        data_type = 'double'
    elif column_type == 'decimal':
        data_type = 'decimal'
    elif column_type in ['date', 'datetime', 'timestamp']:
        data_type = 'date'
    elif column_type in ['string', 'varchar', 'char', 'text', 'longtext']:
        data_type = 'string'

    return data_type



def have_enough_data(bucket_norm_size: int, cur_bucket_size: int, is_first: bool):
    """
    bucket_norm_size: data size / buckets
    cur_bucket_size:
    """
    if is_first:
        return False
    upper_bound = 1.5
    return cur_bucket_size > upper_bound * bucket_norm_size


class HistogramUtils:
    def __init__(self, n, sample_data, table_meta, f = 0.1, k = 10, gamma = 0.1) -> None:
        """
        Histogram utility class
        n: Total number of rows in the original table
        table_meta: Metadata of the table
        sample_data: All sampled data
        f: Error factor, 0 < f < 1
        k: Number of buckets in k-histogram
        gamma: Confidence level, 0 < gamma < 1
        """
        self.f = f
        self.n = n
        self.k = k
        self.gamma = gamma
        self.sample_data = sample_data
        self.table_meta = table_meta
        
        self.table_histogram = self.create_table_histogram()
        self.error_dict = self.comptue_table_max_error_metric(self.table_histogram)
    
    def _get_column_data_type(self, column_name: str) -> str:
        if self.table_meta is None:
            return 'int'
        column_type = None
        for column in self.table_meta.columns:
            if column.name == column_name:
                column_type = column.data_type
        if column_type is None:
            raise ValueError(f"column {column_name} not found in {self.table_meta.columns}")

        data_type = get_column_data_type(column_type)
        if data_type is None:
            raise ValueError(f"column {column_name} data type {column_type} not supported")

        return data_type



    def create_singleton_bucket(self, value_counts: Dict[str, int], data_type) -> List[HistogramBucket]:
        """
        For sampled NDV numbers less than the preset number of buckets, construct one bucket per value.
        value_counts: Result of Counter
        """
        bucket_list = []
        DV_list = sorted(value_counts.keys())
        column_size = sum(list(value_counts.values()))
        curr_size = 0
        for dv in DV_list:
            bucket = {}
            bucket['min_value'] = convert_str_by_type(dv, data_type=data_type)
            bucket['max_value'] = convert_str_by_type(dv, data_type=data_type)
            
            curr_size += value_counts[dv]
            cum_freq = curr_size / column_size
            
            bucket['cum_freq'] = cum_freq
            bucket['row_count'] = 1 # singleton
            bucket['size'] = value_counts[dv]
            bucket_obj = HistogramBucket(bucket['min_value'], bucket['max_value'], bucket['cum_freq'], bucket['row_count'], bucket['size'])
            bucket_list.append(bucket_obj)

        return bucket_list
    
    def create_column_histogram(self, column_name: str) -> List[HistogramBucket]:
        """
        Build a k-histogram for the input column name, dropping NA values.
        """
        column_data = self.sample_data[column_name].dropna()
        bucket_list = []
        if len(self.sample_data) == 0:
            return bucket_list
        
        data_type = self._get_column_data_type(column_name)
        
        value_counts = Counter(column_data.values.tolist()) # {'value': counts}
        DV_list = sorted(value_counts.keys())
        dv_idx = 0
        sampled_ndv = len(DV_list)
        # Sampled NDV is less than or equal to the preset number of buckets
        if sampled_ndv <= self.k:
            return self.create_singleton_bucket(value_counts, data_type)
        
        bucket_norm_size = math.ceil(len(column_data) / self.k)
        cum_freq = 0
        # Construct by bucket, be mindful to exit early
        for i in range(self.k):
            if dv_idx == sampled_ndv:
                break
            # For each bucket, do not exceed the preset size
            current_bucket_size = 0
            bucket = {} # min_value, max_value, cum_freq, row_count, size
            min_value = DV_list[dv_idx]
            max_value = DV_list[dv_idx] 
            row_count = 0
            curr_bucket_val_count = {}
            # ! Do not judge when the first value is added, as it could be skewed data
            is_first = True
            while dv_idx < sampled_ndv and not have_enough_data(bucket_norm_size, current_bucket_size + value_counts[DV_list[dv_idx]], is_first):
                is_first = False
                count = value_counts[DV_list[dv_idx]]
                current_bucket_size += count
                row_count += 1
                max_value = DV_list[dv_idx] 
                curr_bucket_val_count[DV_list[dv_idx]] = count
                dv_idx += 1
            cum_freq += (current_bucket_size / len(column_data))
            bucket_correspond_size = int(current_bucket_size / len(column_data) * self.n)
            curr_bucket_ndv_estimator = NDVEstimator(bucket_correspond_size)
            curr_data_profile = [0] * (current_bucket_size + 1)
            for value, count in curr_bucket_val_count.items():
                curr_data_profile[count] += 1
            est_ndv = curr_bucket_ndv_estimator.estimator(current_bucket_size, curr_data_profile)
            est_ndv = min(est_ndv, bucket_correspond_size)
            
            bucket['min_value'] = convert_str_by_type(min_value, data_type=data_type)
            bucket['max_value'] = convert_str_by_type(max_value, data_type=data_type)
            bucket['cum_freq'] = cum_freq
            bucket['row_count'] = est_ndv # 改为预估的ndv
            bucket['size'] = current_bucket_size
            bucket_obj = HistogramBucket(bucket['min_value'], bucket['max_value'], bucket['cum_freq'], bucket['row_count'], bucket['size'])
            bucket_list.append(bucket_obj)
            
        if dv_idx < sampled_ndv:
            # If there are DVs left, add one more bucket
            bucket = {}
            min_value = DV_list[dv_idx]
            row_count = 0
            curr_bucket_val_count = {}
            while dv_idx < sampled_ndv:
                count = value_counts[DV_list[dv_idx]]
                current_bucket_size += count
                row_count += 1
                curr_bucket_val_count[DV_list[dv_idx]] = count
                dv_idx += 1
            cum_freq += (current_bucket_size / len(column_data))
            bucket_correspond_size = int(current_bucket_size / len(column_data) * self.n)
            curr_bucket_ndv_estimator = NDVEstimator(bucket_correspond_size)
            curr_data_profile = [0] * (current_bucket_size + 1)
            for value, count in curr_bucket_val_count.items():
                curr_data_profile[count] += 1
            est_ndv = curr_bucket_ndv_estimator.estimator(current_bucket_size, curr_data_profile)
            est_ndv = min(est_ndv, bucket_correspond_size)
            max_value = DV_list[dv_idx - 1]
            bucket['min_value'] = convert_str_by_type(min_value, data_type=data_type)
            bucket['max_value'] = convert_str_by_type(max_value, data_type=data_type)
            bucket['cum_freq'] = cum_freq
            bucket['row_count'] = est_ndv # 改为预估的ndv
            bucket['size'] = current_bucket_size
            bucket_obj = HistogramBucket(bucket['min_value'], bucket['max_value'], bucket['cum_freq'], bucket['row_count'], bucket['size'])
            bucket_list.append(bucket_obj)
        return bucket_list
        
    
    def create_table_histogram(self):
        column_names = self.sample_data.columns.to_list()
        histogram_dict = {}
        for column_name in column_names:
            buckets = self.create_column_histogram(column_name)
            data_type = self._get_column_data_type(column_name)
            histogram_type = 'equi-height'
            col_histogram = HistogramStats(buckets=buckets, data_type=data_type, histogram_type=histogram_type)
            histogram_dict[column_name] = col_histogram
        return histogram_dict
    
    def comptue_table_max_error_metric(self, built_histogram) -> Dict[str, float]:
        """Calculate histograms for all columns of the table"""
        column_names = self.sample_data.columns.to_list()
        error_dict = {}
        for column_name in column_names:
            error_dict[column_name] = self.compute_column_max_error_metric(built_histogram, column_name)
        return error_dict
    
    def compute_column_max_error_metric(self, built_histogram, column_name) -> float:
        """
        Given the constructed histogram, calculate the $delta max$ error.
        $ Delta max = max_{1 \leq j \leq k}|b_j - n/k| $
        where b_j is the cardinality of bucket j, there are k buckets in the histogram, and n is the total number of rows in the data.
        """
        max_error = 0
        column_built_histogram = built_histogram[column_name].buckets
        for bucket in column_built_histogram:
            max_error = max(max_error, abs(bucket.size - self.n / self.k))
        return max_error
    
    def compute_delta_error(self, block_size_dict: Dict[str, List[int]]):
        """Calculate the error of the newly sampled results"""
        column_names = self.sample_data.columns.to_list()
        error_dict = {}
        for column_name in column_names:
            error_dict[column_name] = self.compute_column_delta_error(block_size_dict[column_name])
        return error_dict
    
    def compute_column_delta_error(self, block_size_list: List[int]) -> float:
        error = 0
        for block in block_size_list:
            error = max(error, abs(block - self.n / self.k))
        return error
    
    def fit_next_histogram(self, new_sample_data: DataFrame):
        """
        Based on the current histogram, match the histogram of the newly sampled data,
        then calculate the incremental histogram's error under the current histogram
        Input the current sampled data and g to calculate the new histogram's error
        Only allowed to be called during adaptive sampling
        """
        column_names = self.sample_data.columns.to_list()
        current_hist_fit = {}
        for column_name in column_names:
            block_size_list = []
            data_type = self.table_histogram[column_name].data_type
            current_column_data = new_sample_data[column_name].dropna()
            if len(current_column_data) > 0:
                value_counts = Counter(current_column_data.values.tolist()) # {'value': counts}
                DV_list = sorted(value_counts.keys())
                dv_idx = 0
                sampled_ndv = len(DV_list)
                for bucket in self.table_histogram[column_name].buckets:
                    current_bucket_fit_num = 0
                    while dv_idx < sampled_ndv and bucket.min_value <= convert_str_by_type(DV_list[dv_idx], data_type=data_type) and convert_str_by_type(DV_list[dv_idx], data_type=data_type) <= bucket.min_value:
                        current_bucket_fit_num += value_counts[DV_list[dv_idx]]
                        dv_idx += 1
                    block_size_list.append(current_bucket_fit_num)
            
            current_hist_fit[column_name] = block_size_list
        # Obtain information on how the current sample results fit the built histogram, and calculate delta
        fit_error_dict = self.compute_delta_error(current_hist_fit)
        return fit_error_dict
    
    def merge_new_sampled(self, new_sample_data: DataFrame) -> None:
        """Merge the results of the new sampling with the existing sample results"""
        self.sample_data = pd.concat([self.sample_data, new_sample_data], axis=0)
        self.table_histogram = self.create_table_histogram()
        self.error_dict = self.comptue_table_max_error_metric(self.table_histogram)


class NEVUtils:
    def __init__(self) -> None:
        pass
    
    def build_column_profile(self, data: List[Any]):
        """Input all sampled data to construct a profile
        Input all data from the sampled column
        profile: f_j, 1 <= j <= n, n = len(all_sampled_data). f_j represents the number of NDVs that appear j times
            f_0 = 0, as a placeholder
        """
        value_counts = Counter(data)
        data_len = len(data)
        freq = [0] * (data_len + 1)
        for value, count in value_counts.items():
            freq[count] += 1
        return freq
    
    def profile_to_ndv(self, profile: List[int]) -> int:
        """profile， compute NDV d"""
        d = np.sum(profile)
        return d
    
    def compute_error(self, estimated: int, ground_truth: int) -> float:
        """compute q-error"""
        assert estimated > 0 and ground_truth > 0, "estimated and ground_truth NDV must be positive"
        return max(estimated, ground_truth) / min(estimated, ground_truth)
    
    # ==================   estimate NDV by blocks
    def split_list_into_blocks(self, lst, block_size):
        blocks = []
        num_blocks = len(lst) // block_size  # blocks
        for i in range(num_blocks):
            block = lst[i*block_size:(i+1)*block_size]
            blocks.append(block)
        remaining_elements = len(lst) % block_size  # remaining
        if remaining_elements > 0:  # add the last blocks
            last_block = lst[-remaining_elements:]
            blocks.append(last_block)
        return blocks
    def collapse_block(self, block):
        # Collapse all multiple occurrences of a value within a block into one
        # occurrence. Return the resulting distinc values.
        distinct_values = []
        seen = set()
        for value in block:
            if value not in seen:
                distinct_values.append(value)
                seen.add(value)
        return distinct_values
    def split_list(self, lst, n):
        # n is too large
        if n > len(lst):
            return [lst]
        
        # calculate the length of each group
        group_size = len(lst) // n
        remainder = len(lst) % n

        # initialize the result list
        result = []

        # iterate over the range of n groups
        for i in range(n):
            # determine the size of the current group
            size = group_size + (1 if i < remainder else 0)
            # get the current group by slicing the input list
            group = lst[:size]
            # add the current group to the result list
            result.append(group)
            # update the input list by removing the elements of the current group
            lst = lst[size:]

        return result
    def split_half(self, list_data):
        if len(list_data) == 1:
            return list_data[:1], []
        half = len(list_data)//2
        return list_data[:half], list_data[half:]
    def estimate_ndv_with_split(self, collapse_data, sample_fraction):
        # half collapse
        collapse_half_left, collapse_half_right = self.split_half(collapse_data)
        
        # ndv of half
        collapse_ndv_half = len(set(collapse_half_left))

        # ndv of total
        collapse_ndv_total = len(set(collapse_data))

        # rate
        rate = collapse_ndv_total / collapse_ndv_half
        # rate
        if rate < 1.1:
            return collapse_ndv_total

        #return collapse_ndv_total / self.sample_fraction
        return (collapse_ndv_total / sample_fraction) * (rate - 1) 
class NDVEstimator:
    def __init__(self, original_num) -> None:
        self.original_num = original_num # 原表行数
        self.tools = NEVUtils()
        
    def estimator(self, r: int, profile: List[int], method: str = 'GEE'):
        """[error_bound, GEE, Chao, scale, shlosser, ChaoLee, LS]
        """
        if method == 'error_bound':
            ndv = self.error_bound_estimate(r, profile)
        elif method == 'GEE':
            ndv = self.gee_estimate(r, profile)
        elif method == 'Chao':
            ndv = self.chao_estimate(r, profile)
        elif method == 'scale':
            ndv = self.scale_estimate(r, profile)
        elif method == 'shlosser':
            ndv = self.shlosser_estimate(r, profile)
        elif method == 'ChaoLee':
            ndv = self.ChaoLee_estimate(r, profile)
        elif method == 'LS':
            ndv = self.LS_estimate(profile)
        else:
            raise ValueError(f"Unsupported NDV estimation method: {method}")
        return ndv

    def estimate(self, all_sampled_data: DataFrame) -> Dict[str, float]:
        """input all data and estimate NDV
        """
        columns = all_sampled_data.columns
        ndv_dict = {}
        data_len = len(all_sampled_data)
        for column in columns:
            col_data = all_sampled_data[column].dropna().values.tolist()
            profile = self.build_column_profile(col_data)
            if len(profile) <= 1:
                ndv_dict[column] = 0.01 # 没采到数据，直接返回0.01，不让ndv为0，影响后续计算
                continue
            ndv = self.estimator(data_len, profile)
            ndv_dict[column] = ndv
        return ndv_dict
    
    def  build_column_profile(self, data: List[Any]):
        return self.tools.build_column_profile(data)
    
    def scale_estimate(self, r: int, profile: List[int]):
        """e=n/r * d
        This method assumes that the sampled data is completely randomly and uniformly sampled from the original data
        """
        factor = self.original_num / r
        d = self.tools.profile_to_ndv(profile)
        return d * factor
    
    def block_split_estimate(self, tuple_list):
        """
        the first version
        """
        block_size = 100
        data_blocks = self.tools.split_list_into_blocks(tuple_list, block_size)
        collapsed_sample = []
        for block in data_blocks:
            collapsed_block = self.tools.collapse_block(block)
            collapsed_sample.extend(collapsed_block)
        ndv_sample_data = len(set(collapsed_sample))
        len_blocks = len(data_blocks)
        ndv_perblock = ndv_sample_data / len_blocks
        
        group_list = self.tools.split_list(collapsed_sample, 10)
        # ndv for each group
        ndv_list = []
        for group in group_list:
            ndv = self.tools.estimate_ndv_with_split(group, self.original_num / len(tuple_list))
            ndv_list.append(ndv)

        # mean and variance
        mean = np.mean(ndv_list)
        return mean
        
    def error_bound_estimate(self, r: int, profile: List[int]):
        """e=sqrt{{n}/{r}} f_1^{+}+sum_{j=2}^r f_j, 1 <= j <= r
        """
        scale_factor = math.sqrt(self.original_num / r)
        estimated = np.sum(profile) - profile[1]
        estimated += scale_factor * max(profile[1], 1)
        
        return estimated
    
    def gee_estimate(self, r: int, profile: List[int]):
        """e=sqrt{{n}/{r}} f_1+sum_{j=2}^r f_j, 1 <= j <= r
        """
        scale_factor = math.sqrt(self.original_num / r)
        estimated = np.sum(profile) - profile[1]
        estimated += scale_factor * profile[1]
        
        return estimated
    
    def chao_estimate(self, r: int, profile: List[int]):
        """e=d+f_1^2/f_2, 1 <= j <= r
        """
        d = self.tools.profile_to_ndv(profile)
        if len(profile) <= 2:
            estimated = self.scale_estimate(r, profile)
        elif profile[2] == 0:
            estimated = self.scale_estimate(r, profile)
        else:
            estimated = d + math.pow(profile[1], 2) / profile[2]
        return estimated
    
    def shlosser_estimate(self, r: int, profile: List[int]):
        d = self.tools.profile_to_ndv(profile)
        q = r / self.original_num
        sum1 = 0
        sum2 = 0
        for i in range(1, len(profile)):
            sum1 += profile[i] * math.pow(1-q, i)
            sum2 += profile[i] * math.pow(1-q, i-1) * i * q
        sum1 *= profile[1]
        if sum2 == 0:
            estimated = d
        else:
            estimated = d + sum1 / sum2
        return estimated
            
    def ChaoLee_estimate(self, r: int, profile: List[int]):
        d = self.tools.profile_to_ndv(profile)
        if profile[1] == self.original_num:
            return self.scale_estimate(r, profile)
        c_hat = 1 - profile[1] / self.original_num
        tmp = [i for i in profile if i != 0]
        if len(tmp) <= 1:
            gamma_2 = 0
        else:
            gamma_2 = np.var(tmp) / self.original_num / self.original_num
        estimated = d / c_hat + r * (1 - c_hat) * gamma_2 / c_hat
        return estimated
    
    def LS_estimate(self, profile: List[int]):
        estimator = ndvEstimator()
        estimated = estimator.profile_predict(f=profile, N=self.original_num)
        return estimated
    
    def estiamte_multi_columns(self, all_sampled_data: DataFrame, target_columns: List[str], method='error_bound') -> float:
        if target_columns[0] not in all_sampled_data.columns:
            target_columns = [target_column.upper() for target_column in target_columns]
        if not all(col in all_sampled_data.columns for col in target_columns):
            return 10
        tuple_list = list(zip(*[all_sampled_data[col] for col in target_columns]))
        profile = self.build_column_profile(tuple_list)
        if method == 'block_split':
            ndv = self.block_split_estimate(tuple_list)
        else:
            ndv = self.estimator(len(all_sampled_data), profile, method)
        return ndv


def load_sample_relative_path(relative_path: str, local_sample_path) -> pd.DataFrame:
    local_file_path = os.path.join(local_sample_path, relative_path)
    if not os.path.exists(local_file_path):
        logging.info(f"sample file doesn't exist. {local_file_path=}")
        return None
    if local_file_path.endswith('.csv'):
        return pd.read_csv(local_file_path)
    return pd.read_parquet(local_file_path)


def load_sample_file(table_stats: VidexTableStats):
    """Called in VIDEX, load the sample file through the passed file information"""
    table_name = table_stats.table_name
    db_name = table_stats.dbname
    sample_file_info = table_stats.sample_file_info
    save_file_list = sample_file_info.sample_file_dict.get(db_name).get(table_name)
    df_sample_raw = load_sample_relative_path(save_file_list[0],
                                              local_sample_path=sample_file_info.local_path_prefix,)
    return df_sample_raw


if __name__ == '__main__':
    estimator = NDVEstimator(10000)
    ndv_methods = ['error_bound', 'GEE', 'Chao', 'scale', 'block_split', 'LS']
    test_data = {'test': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 1, 2]}
    df = pd.DataFrame(test_data)
    for method in ndv_methods:
        ndv = estimator.estiamte_multi_columns(df, ['test'], method)
        print(f"{method}: {ndv}")
