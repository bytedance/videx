# -*- coding: utf-8 -*-
"""
Copyright (c) 2024 Bytedance Ltd. and/or its affiliates
SPDX-License-Identifier: MIT
"""
import math
from math import factorial
from collections import Counter
from typing import List, Any, Dict

import numpy as np
from estndv import ndvEstimator
from pandas import DataFrame

from adandv_model_infer import AdaNDVPredictor, AdaNDVConfig

from sub_platforms.sql_opt.videx.videx_utils import safe_tolist


class NEVUtils:
    def __init__(self) -> None:
        pass

    def build_column_profile(self, data: List[Any]):
        """
        Input all sampled data to construct a profile
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
        remaining_elements = len(lst) % block_size
        if remaining_elements > 0:  # remaining some elements, add the last block
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
        self.ada_model = None

    def estimator(self, r: int, profile: List[int], method: str = 'GEE'):
        """
        [error_bound, GEE, Chao, scale, shlosser, ChaoLee, LS]
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
        elif method == 'Goodman':
            ndv = self.Goodman_estimate(r, profile)
        elif method == 'Jackknife':
            ndv = self.Jackknife_estimate(r, profile)
        elif method == 'Sichel':
            ndv = self.Sichel_estimate(r, profile)
        elif method == 'Method of Movement':
            ndv = self.Method_of_Movement_estimate(r, profile)
        elif method == 'Bootstrap':
            ndv = self.Bootstrap_estimate(r, profile)
        elif method == 'Horvitz Thompson':
            ndv = self.Horvitz_Thompson_estimate(r, profile)
        elif method == 'Method of Movement v2':
            ndv = self.Method_of_Movement_v2_estimate(r, profile)
        elif method == 'Method of Movement v3':
            ndv = self.Method_of_Movement_v3_estimate(r, profile)
        elif method == 'Smoothed Jackknife':
            ndv = self.Smoothed_Jackknife_estimate(r, profile)
        elif method == 'Ada':
            if self.ada_model is None:
                sample_rate = r / self.original_num
                config = AdaNDVConfig(
                    model_path="src/sub_platforms/sql_opt/histogram/resources/adandv.pth",
                    model_input_len=100,
                    estimator_num=9,
                    k=2,
                    sample_rate=sample_rate
                )
                self.ada_model = AdaNDVPredictor(config)
            ndv = self.ada_estimate(r, profile)
        else:
            raise ValueError(f"Unsupported NDV estimation method: {method}")
        return ndv


    def ada_estimate(self, r: int, profile: List[int]):
        estimate_list = []
        base_methods = [
            'error_bound', 'GEE', 'Chao', 'shlosser', 'ChaoLee',
            'Jackknife', 'Sichel',
            'Method of Movement', 'Bootstrap'
        ] 
        # ['error_bound', 'GEE', 'Chao', 'shlosser', 'ChaoLee', 'jackknife', 'sichel', 'method_of_movement', 'bootstrap']

        for method in base_methods:
            try:
                estimate = self.estimator(r, profile, method)
            except Exception:
                estimate = sum(profile[i] for i in range(1, len(profile)))  # fallback if method not implemented fallback = d, d defaults to the sum of each bit of the sampled profile
            estimate_list.append(estimate)

        ndv = self.ada_model.predict(profile, estimate_list)
        return ndv
    

    def estimate(self, all_sampled_data: DataFrame) -> Dict[str, float]:
        """input all data and estimate NDV
        """
        columns = all_sampled_data.columns
        ndv_dict = {}
        data_len = len(all_sampled_data)
        for column in columns:
            col_data = safe_tolist(all_sampled_data[column].dropna())
            profile = self.build_column_profile(col_data)
            if len(profile) <= 1:
                ndv_dict[column] = 0.01 # 没采到数据，直接返回0.01，不让ndv为0，影响后续计算
                continue
            ndv = self.estimator(data_len, profile)
            ndv_dict[column] = ndv
        return ndv_dict

    def  build_column_profile(self, data: List[Any]):
        """input all sampling data to construct profile"""
        return self.tools.build_column_profile(data)



    def Goodman_estimate(self, r: int, profile: List[int]):
        """
        Goodman estimator based on the profile of frequencies.
        
        Args:
            r (int): total number of observed tuples (sample size).
            profile (List[int]): profile[i] is the number of distinct values that appear i times.

        Returns:
            float: estimated number of distinct values in the full population.
        """
        n = r  # total number of elements
        d = self.tools.profile_to_ndv(profile)  # total number of distinct elements observed
        if n == d:
            return d  # All values are unique
        
        N = getattr(self, "original_num", 2 * r) 
        memo = {}

        def fact(x):
            if x not in memo:
                memo[x] = factorial(x)
            return memo[x]
        
        sum_goodman = 0

        for i in range(1, len(profile)):
            f_i = profile[i]
            if f_i == 0:
                continue
            try:
                num = fact(N - n + i - 1) * fact(n - i)
                denom = fact(N - n - 1) * fact(n)
                sum_goodman += ((-1) ** (i + 1)) * num * f_i / denom
            except (ValueError, OverflowError):
                continue
        
        return d + sum_goodman

    def Jackknife_estimate(self, r: int, profile: List[int]):
        """
        Jackknife estimator
        \hat{D}_{jack} = d + (n - 1) * f1 / n
        where:
        - d: observed distinct count
        - f1: frequency of singleton values (appeared once)
        """

        d = self.tools.profile_to_ndv(profile)
        if r == 0 or d == 0:
            return 0.0
        f1 = profile[1] if len(profile) > 1 else 0
        return d + (r - 1) * f1 / r


    def Sichel_estimate(self, r: int, profile: List[int]):
        """
        Sichel's estimator
        Uses zero-truncated GIG-Poisson model with parameter solving.
        """
        d = self.tools.profile_to_ndv(profile)
        if r == 0 or d == 0:
            return 0.0
        f1 = profile[1] if len(profile) > 1 else 0
        if f1 == 0 or r == d:
            return float(d)  # fallback to observed distinct count

        a = (2 * r) / d - np.log(r / f1)
        b = (2 * f1) / d + np.log(r / f1)

        def eq(g):
            return (1 + g) * np.log(g) - a * g + b

        candidates = []
        # Warning.filterwarnings("ignore")

        for init_g in np.linspace((f1 / r) + 1e-5, 0.999999, 20):
            try:
                g = float(broyden2(eq, init_g))
                if not (f1 / r < g < 1):
                    continue
                b_hat = g * np.log((r * g) / f1) / (1 - g)
                c_hat = (1 - g ** 2) / (r * g ** 2)
                d_sichel = 2 / (b_hat * c_hat)
                candidates.append(d_sichel)
            except:
                continue


        if not candidates:
            return float(d)
        return min(candidates)

    def Method_of_Movement_estimate(self, r: int, profile: List[int]):
        """
        Method of Moments Estimator:
        Estimates the total number of distinct values D using observed distinct count d and sample size r.
        Equation: d = D * (1 - exp(-r / D)) => solve for D
        """
        d = self.tools.profile_to_ndv(profile)     # profile: freq histogram (e.g., [0, f1, f2, f3, ...])
        if d == r:
            return d  # all values are distinct

        def eq(D):
            return D * (1 - math.exp(-r / D)) - d

        # Try both solvers independently for better robustness
        solutions = []
        
        try:
            d1 = broyden1(eq, d)
            solutions.append(d1)
        except:
            pass
        
        try:
            d2 = broyden2(eq, d)
            solutions.append(d2)
        except:
            pass
        
        # Return best solution if any succeeded, otherwise fallback to observed count
        return min(solutions) if solutions else d

    def Bootstrap_estimate(self, r: int, profile: List[int]):
        """
        Bootstrap Estimator:
        Estimates the number of distinct values D using a bootstrap-based adjustment.
        D_boot = d + sum_j (1 - n_j / r)^r
        """
        d = self.tools.profile_to_ndv(profile)
        if d == r:
            return d  # all values are distinct

        result = d
        for freq, count in enumerate(profile):
            if freq == 0:
                continue
            result += count * ((1 - freq / r) ** r)
        return result

    def Horvitz_Thompson_estimate(self, r: int, profile: List[int]):
        """
        Horvitz-Thompson Estimator:
        Estimates the total number of distinct values D using inverse inclusion probabilities.
        D_HT = sum_i 1 / (1 - (1 - 1/N)^n_i)
        """
        N = self.original_num
        estimate = 0.0
        for freq, count in enumerate(profile):
            if freq == 0:
                continue
            inclusion_prob = 1.0 - (1.0 - 1.0 / N) ** freq
            if inclusion_prob <= 0:
                continue
            estimate += count / inclusion_prob
        return estimate

    def Method_of_Movement_v2_estimate(self, r: int, profile: List[int]):
        """
            do not cache gamma
        """
        n = r
        d = self.tools.profile_to_ndv(profile)
        N = self.original_num

        def h_x(x: float, n: int, N: int) -> float:
            gamma_num_1 = math.lgamma(N - x + 1)
            gamma_num_2 = math.lgamma(N - n + 1)
            gamma_denom_1 = math.lgamma(N - x - n + 1)
            gamma_denom_2 = math.lgamma(N + 1)
            return math.exp(gamma_num_1 + gamma_num_2 - gamma_denom_1 - gamma_denom_2)

        def f(D: float) -> float:
            return D * (1 - h_x(N / D, n, N)) - d

        try:
            root1 = broyden1(f, d)
            root2 = broyden2(f, d)
            return min(root1, root2)
        except Exception:
            return d

    def Method_of_Movement_v3_estimate(self, r: int, profile: List[int]):
        n = r
        d = self.tools.profile_to_ndv(profile)
        N = self.original_num

        # Step 1: Estimate D_v2 first
        D_v2 = self.Method_of_Movement_v2_estimate(r, profile)
        if D_v2 == 0:
            return d
        N_tilde = N / D_v2

        # Step 2: Compute gamma_hat_squared (coefficient of variation squared)
        mean_freq = sum(profile) / len(profile)
        variance_freq = sum((x - mean_freq) ** 2 for x in profile) / len(profile)
        gamma_hat_squared = variance_freq / (mean_freq ** 2)

        # Step 3: h(N_tilde)
        def h_x(x: float, n: int, N: int) -> float:
            gamma_num_1 = math.lgamma(N - x + 1)
            gamma_num_2 = math.lgamma(N - n + 1)
            gamma_denom_1 = math.lgamma(N - x - n + 1)
            gamma_denom_2 = math.lgamma(N + 1)
            return math.exp(gamma_num_1 + gamma_num_2 - gamma_denom_1 - gamma_denom_2)

        h_val = h_x(N_tilde, n, N)

        # Step 4: Compute g_n(N_tilde)
        def g_n(x: float, n: int, N: int) -> float:
            return sum(1 / (N - x - n + k) for k in range(n))

        g_val = g_n(N_tilde, n, N)

        # Step 5: Compute correction term
        correction = 0.5 * (N_tilde ** 2) * gamma_hat_squared * D_v2 * h_val * (g_val - g_val ** 2)

        # Final D_v3 estimate
        denominator = 1 - h_val + correction
        if denominator == 0:
            return d
        return d / denominator

    def Smoothed_Jackknife_estimate(self, r: int, profile: List[int]):
        n = r
        d = self.tools.profile_to_ndv(profile)
        f1 = profile[1] if len(profile) > 1 else 0
        if f1 == 0 or n == 0:
            return d

        N = self.original_num
        d0 = d - f1 / n
        correction = (N - n + 1) * f1 / (n * N)
        d_hat_0 = d0 / (1 - correction)

        weights = [1 / i for i in range(1, d + 1)]
        bias = sum(weights) / d

        d_hat = d_hat_0 / (1 - bias)
        return d_hat
    
    def scale_estimate(self, r: int, profile: List[int]):
        """
        e=n/r * d
        r: sampling rows
        This method assumes that the sampled data is completely randomly and uniformly sampled from the original data
        """
        factor = self.original_num / r
        d = self.tools.profile_to_ndv(profile)
        return d * factor

    def block_split_estimate(self, tuple_list):
        """
        sqlbrain初版NDV估计算法
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
        输入采样行数和对应的profile，返回估计的NDV
        r: 采样行数
        """
        scale_factor = math.sqrt(self.original_num / r)
        estimated = np.sum(profile) - profile[1]
        estimated += scale_factor * max(profile[1], 1)

        return estimated

    def gee_estimate(self, r: int, profile: List[int]):
        """e=sqrt{{n}/{r}} f_1+sum_{j=2}^r f_j, 1 <= j <= r
        输入采样行数和对应的profile，返回估计的NDV
        r: 采样行数
        """
        scale_factor = math.sqrt(self.original_num / r)
        estimated = np.sum(profile) - profile[1]
        estimated += scale_factor * profile[1]

        return estimated

    def chao_estimate(self, r: int, profile: List[int]):
        """e=d+f_1^2/f_2, 1 <= j <= r
        输入采样行数和对应的profile，返回估计的NDV
        r: 采样行数
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

    def estimate_multi_columns(self, all_sampled_data: DataFrame, target_columns: List[str], method='error_bound') -> float:
        """输入全部的采样数据和目标列（可以为多列），估计其NDV"""
        if target_columns[0] not in all_sampled_data.columns:
            target_columns = [target_column.upper() for target_column in target_columns]
        # 暂时忽略没有采样的列，返回mock值10
        if not all(col in all_sampled_data.columns for col in target_columns):
            # 如果出现缺列，我们倾向于高估其代价。这意味着 ndv(col) as 1, cardinality as table_rows
            # 过滤 target_columns，我们仅估计 all_sampled_data.columns 中有的数据
            target_columns = [col for col in target_columns if col in all_sampled_data.columns]
            if len(target_columns) == 0:
                return 1
        tuple_list = list(zip(*[all_sampled_data[col] for col in target_columns]))
        profile = self.build_column_profile(tuple_list)
        if method == 'block_split':
            ndv = self.block_split_estimate(tuple_list)
        else:
            ndv = self.estimator(len(all_sampled_data), profile, method)
        return ndv
