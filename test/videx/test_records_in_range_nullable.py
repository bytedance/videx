# -*- coding: utf-8 -*-
"""
Copyright (c) 2024 Bytedance Ltd. and/or its affiliates
SPDX-License-Identifier: MIT
"""
import json
import os
import unittest
from typing import List

from sub_platforms.sql_opt.videx.videx_histogram import HistogramBucket, HistogramStats, init_bucket_by_type
from sub_platforms.sql_opt.videx.videx_metadata import construct_videx_task_meta_from_local_files
from sub_platforms.sql_opt.videx.videx_service import VidexSingleton
from sub_platforms.sql_opt.videx.videx_utils import IndexRangeCond, GT_Table_Return, load_json_from_file, \
    BTreeKeyOp, BTreeKeySide, join_path


class Test_record_in_ranges_algorithm(unittest.TestCase):
    """
    测试在 histogram 包含 null 值时，records_in_range 算法的表现
    """

    def setUp(self):
        self.singleton = VidexSingleton()
        req_dict = load_json_from_file(join_path(__file__, 'data/videx_metadata_test_null_db.json'))

        meta = construct_videx_task_meta_from_local_files(task_id=None,
                                                          videx_db='videx_test_null_db',
                                                          stats_file=req_dict.get('stats_dict', {}),
                                                          hist_file=req_dict.get('hist_dict', {}),
                                                          ndv_single_file=req_dict.get('ndv_single_dict', {}),
                                                          ndv_mulcol_file=req_dict.get('ndv_mulcol_dict', {}),
                                                          gt_rec_in_ranges_file=None,
                                                          gt_req_resp_file=None,
                                                          raise_error=True,
                                                          )
        self.singleton.add_task_meta(meta.to_dict())

    def test_gt_NULL_and_lt_empty_str(self):
        """
        explain select nullable_code from test_columns where nullable_code != '';

        data: 50% NULL, 10% 'A', 10% 'B', 10% 'C', 10% 'D', 10% 'E'
        this trace: NULL < nullable_code < ''

        Returns:
            freq is 0, take max(1, freq), so return 1

        """
        req_json = {"item_type": "videx_request",
                    "properties": {"dbname": "videx_test_null_db",
                                   "function": "virtual ha_rows ha_videx::records_in_range(uint, key_range *, key_range *)",
                                   "table_name": "test_columns",
                                   "target_storage_engine": "INNODB",
                                   "videx_options": "{}"
                                   },
                    "data": [
                        {"item_type": "min_key",
                         "properties": {"index_name": "idx_nullable_code", "length": "5", "operator": ">"},
                         "data": [{"item_type": "column_and_bound",
                                   "properties": {"column": "nullable_code", "value": "NULL"},
                                   "data": []}]},
                        {"item_type": "max_key",
                         "properties": {"index_name": "idx_nullable_code", "length": "5", "operator": "<"},
                         "data": [
                             {"item_type": "column_and_bound", "properties": {"column": "nullable_code", "value": "''"},
                              "data": []}]}
                    ]}
        res = self.singleton.ask(
            req_json_item=req_json,
            raise_out=True
        )
        print(res)
        self.assertEqual(res, (200, 'OK', {'value': '1'}))

    def test_eq_NULL(self):
        """
        data: 50% NULL, 10% 'A', 10% 'B', 10% 'C', 10% 'D', 10% 'E'

        explain select nullable_code from test_columns where nullable_code is NULL;

        trace condition: nullable_code = NULL

        Returns:

        """
        req_json = {"item_type": "videx_request",
                    "properties": {"dbname": "videx_test_null_db",
                                   "function": "virtual ha_rows ha_videx::records_in_range(uint, key_range *, key_range *)",
                                   "table_name": "test_columns",
                                   "target_storage_engine": "INNODB",
                                   "videx_options": "{}"},
                    "data": [
                        {"item_type": "min_key",
                         "properties": {"index_name": "idx_nullable_code", "length": "5", "operator": "="},
                         "data": [{"item_type": "column_and_bound",
                                   "properties": {"column": "nullable_code", "value": "NULL"},
                                   "data": []}]},
                        {"item_type": "max_key",
                         "properties": {"index_name": "idx_nullable_code", "length": "5", "operator": ">"},
                         "data": [{"item_type": "column_and_bound",
                                   "properties": {"column": "nullable_code", "value": "NULL"},
                                   "data": []}]}]}
        res = self.singleton.ask(
            req_json_item=req_json,
            raise_out=True
        )
        print(res)
        self.assertEqual(res, (200, 'OK', {'value': '25'}))


    def test_neq_NULL(self):
        """
        data: 50% NULL, 10% 'A', 10% 'B', 10% 'C', 10% 'D', 10% 'E'

        explain select nullable_code from test_columns where nullable_code is not NULL;

        trace condition: NULL < nullable_code

        Returns:

        """
        req_json = {"item_type": "videx_request",
                    "properties": {
                        "dbname": "videx_test_null_db",
                        "function": "virtual ha_rows ha_videx::records_in_range(uint, key_range *, key_range *)",
                        "table_name": "test_columns", "target_storage_engine": "INNODB", "videx_options": "{}"},
                    "data": [{"item_type": "min_key",
                              "properties": {"index_name": "idx_nullable_code", "length": "5", "operator": ">"},
                              "data": [{"item_type": "column_and_bound",
                                        "properties": {"column": "nullable_code", "value": "NULL"}, "data": []}]},
                             {"item_type": "max_key", "properties": {}, "data": []}
                             ]}

        res = self.singleton.ask(
            req_json_item=req_json,
            raise_out=True
        )
        print(res)
        self.assertEqual(res, (200, 'OK', {'value': '25'}))
