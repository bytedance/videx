# -*- coding: utf-8 -*-
"""
Copyright (c) 2024 Bytedance Ltd. and/or its affiliates
SPDX-License-Identifier: MIT
"""
import unittest

from pandas import DataFrame

from sub_platforms.sql_opt.histogram.ndv_estimator import NDVEstimator


class TestNDVEstimator(unittest.TestCase):
    def test_multi_column_independent_estimate(self):
        estimator = NDVEstimator(original_num=1000)
        estimator.estimator = lambda *args, **kwargs: 10
        sampled_data = DataFrame({"a": range(10), "b": range(10)})

        actual = estimator._estimate_multi_columns_independent(
            sampled_data, ["a", "b"], "scale"
        )

        self.assertEqual(actual, 100)

    def test_multi_column_independent_estimate_is_capped_by_rows(self):
        estimator = NDVEstimator(original_num=1000)
        estimator.estimator = lambda *args, **kwargs: 100
        sampled_data = DataFrame({"a": range(10), "b": range(10)})

        actual = estimator._estimate_multi_columns_independent(
            sampled_data, ["a", "b"], "scale"
        )

        self.assertEqual(actual, 1000)


if __name__ == '__main__':
    unittest.main()
