# -*- coding: utf-8 -*-
"""
Copyright (c) 2024 Bytedance Ltd. and/or its affiliates
SPDX-License-Identifier: MIT
"""
import os.path
import unittest
from datetime import datetime, date

import numpy as np
import pandas as pd

from sub_platforms.sql_opt.meta import TableId
from sub_platforms.sql_opt.videx.videx_utils import compare_explain, load_json_from_file, search_videx_http_dict, \
    construct_involved_db_tables, parse_datetime, reformat_datetime_str, is_datetime_like


class Test(unittest.TestCase):
    def test_compare_explain_same(self):
        explain_with_idx_innodb = [
            {
                "id": 1,
                "select_type": "SIMPLE",
                "table": "customer",
                "partitions": None,
                "type": "ref",
                "possible_keys": "PRIMARY,idx_C_MKTSEGMENT_C_CUSTKEY",
                "key": "idx_C_MKTSEGMENT_C_CUSTKEY",
                "key_len": "40",
                "ref": "const",
                "rows": 1964,
                "filtered": 100.0,
                "Extra": "Using where; Using index; Using temporary; Using filesort"
            },
            {
                "id": 1,
                "select_type": "SIMPLE",
                "table": "orders",
                "partitions": None,
                "type": "ref",
                "possible_keys": "PRIMARY,ORDERS_FK1,idx_O_ORDERKEY_O_ORDERDATE,idx_O_CUSTKEY_O_ORDERKEY_O_ORDERDATE,idx_O_ORDERKEY_O_CUSTKEY_O_ORDERDATE,idx_O_ORDERDATE",
                "key": "ORDERS_FK1",
                "key_len": "4",
                "ref": "tpch.customer.C_CUSTKEY",
                "rows": 1,
                "filtered": 44.34,
                "Extra": "Using where"
            },
            {
                "id": 1,
                "select_type": "SIMPLE",
                "table": "lineitem",
                "partitions": None,
                "type": "ref",
                "possible_keys": "LINEITEM_UK1,LINEITEM_FK1,idx_L_ORDERKEY_L_SHIPDATE,idx_L_ORDERKEY_L_SUPPKEY,idx_L_SHIPDATE",
                "key": "LINEITEM_UK1",
                "key_len": "4",
                "ref": "tpch.orders.O_ORDERKEY",
                "rows": 3,
                "filtered": 55.52,
                "Extra": "Using where"
            }
        ]
        explain_with_idx_videx_with_gt = [
            {
                "id": 1,
                "select_type": "SIMPLE",
                "table": "customer",
                "partitions": None,
                "type": "ref",
                "possible_keys": "PRIMARY,idx_C_MKTSEGMENT_C_CUSTKEY",
                "key": "idx_C_MKTSEGMENT_C_CUSTKEY",
                "key_len": "40",
                "ref": "const",
                "rows": 1964,
                "filtered": 100.0,
                "Extra": "Using where; Using index; Using temporary; Using filesort"
            },
            {
                "id": 1,
                "select_type": "SIMPLE",
                "table": "orders",
                "partitions": None,
                "type": "ref",
                "possible_keys": "PRIMARY,ORDERS_FK1,idx_O_ORDERKEY_O_ORDERDATE,idx_O_CUSTKEY_O_ORDERKEY_O_ORDERDATE,idx_O_ORDERKEY_O_CUSTKEY_O_ORDERDATE,idx_O_ORDERDATE",
                "key": "ORDERS_FK1",
                "key_len": "4",
                "ref": "tpch.customer.C_CUSTKEY",
                "rows": 1,
                "filtered": 44.34,
                "Extra": "Using where"
            },
            {
                "id": 1,
                "select_type": "SIMPLE",
                "table": "lineitem",
                "partitions": None,
                "type": "ref",
                "possible_keys": "LINEITEM_UK1,LINEITEM_FK1,idx_L_ORDERKEY_L_SHIPDATE,idx_L_ORDERKEY_L_SUPPKEY,idx_L_SHIPDATE",
                "key": "LINEITEM_UK1",
                "key_len": "4",
                "ref": "tpch.orders.O_ORDERKEY",
                "rows": 3,
                "filtered": 55.52,
                "Extra": "Using where"
            }
        ]
        res = compare_explain(expect=explain_with_idx_innodb, actual=explain_with_idx_videx_with_gt)
        print(res)
        self.assertDictEqual({'score': 1.0, 'msg': '', 'diff': {}}, res)

    def test_compare_explain_diff_length(self):
        explain_with_idx_innodb = [
            {
                "id": 1,
                "select_type": "SIMPLE",
                "table": "orders",
                "partitions": None,
                "type": "ref",
                "possible_keys": "PRIMARY,ORDERS_FK1,idx_O_ORDERKEY_O_ORDERDATE,idx_O_CUSTKEY_O_ORDERKEY_O_ORDERDATE,idx_O_ORDERKEY_O_CUSTKEY_O_ORDERDATE,idx_O_ORDERDATE",
                "key": "ORDERS_FK1",
                "key_len": "4",
                "ref": "tpch.customer.C_CUSTKEY",
                "rows": 1,
                "filtered": 44.34,
                "Extra": "Using where"
            },
            {
                "id": 1,
                "select_type": "SIMPLE",
                "table": "lineitem",
                "partitions": None,
                "type": "ref",
                "possible_keys": "LINEITEM_UK1,LINEITEM_FK1,idx_L_ORDERKEY_L_SHIPDATE,idx_L_ORDERKEY_L_SUPPKEY,idx_L_SHIPDATE",
                "key": "LINEITEM_UK1",
                "key_len": "4",
                "ref": "tpch.orders.O_ORDERKEY",
                "rows": 3,
                "filtered": 55.52,
                "Extra": "Using where"
            }
        ]
        explain_with_idx_videx_with_gt = [
            {
                "id": 1,
                "select_type": "SIMPLE",
                "table": "customer",
                "partitions": None,
                "type": "ref",
                "possible_keys": "PRIMARY,idx_C_MKTSEGMENT_C_CUSTKEY",
                "key": "idx_C_MKTSEGMENT_C_CUSTKEY",
                "key_len": "40",
                "ref": "const",
                "rows": 1964,
                "filtered": 100.0,
                "Extra": "Using where; Using index; Using temporary; Using filesort"
            },
            {
                "id": 1,
                "select_type": "SIMPLE",
                "table": "orders",
                "partitions": None,
                "type": "ref",
                "possible_keys": "PRIMARY,ORDERS_FK1,idx_O_ORDERKEY_O_ORDERDATE,idx_O_CUSTKEY_O_ORDERKEY_O_ORDERDATE,idx_O_ORDERKEY_O_CUSTKEY_O_ORDERDATE,idx_O_ORDERDATE",
                "key": "ORDERS_FK1",
                "key_len": "4",
                "ref": "tpch.customer.C_CUSTKEY",
                "rows": 1,
                "filtered": 44.34,
                "Extra": "Using where"
            },
            {
                "id": 1,
                "select_type": "SIMPLE",
                "table": "lineitem",
                "partitions": None,
                "type": "ref",
                "possible_keys": "LINEITEM_UK1,LINEITEM_FK1,idx_L_ORDERKEY_L_SHIPDATE,idx_L_ORDERKEY_L_SUPPKEY,idx_L_SHIPDATE",
                "key": "LINEITEM_UK1",
                "key_len": "4",
                "ref": "tpch.orders.O_ORDERKEY",
                "rows": 3,
                "filtered": 55.52,
                "Extra": "Using where"
            }
        ]
        res = compare_explain(expect=explain_with_idx_innodb, actual=explain_with_idx_videx_with_gt)
        print(res)
        self.assertDictEqual(
            {'score': 0.0, 'msg': 'length of explain items in expect and actual do not match.', 'diff': {}}, res)

    def test_compare_explain_diff(self):
        explain_with_idx_innodb = [
            {
                "id": 1,
                "select_type": "SIMPLE",
                "table": "customer",
                "partitions": None,
                "type": "ref",
                "possible_keys": "PRIMARY,idx_C_MKTSEGMENT_C_CUSTKEY",
                "key": "idx_C_MKTSEGMENT_C_CUSTKEY",
                "key_len": "40",
                "ref": "const",
                "rows": 1964,
                "filtered": 100.0,
                "Extra": "Using where; Using index; Using temporary; Using filesort"
            },
            {
                "id": 1,
                "select_type": "SIMPLE",
                "table": "orders",
                "partitions": None,
                "type": "ref",
                "possible_keys": "PRIMARY,ORDERS_FK1,idx_O_ORDERKEY_O_ORDERDATE,idx_O_CUSTKEY_O_ORDERKEY_O_ORDERDATE,idx_O_ORDERKEY_O_CUSTKEY_O_ORDERDATE,idx_O_ORDERDATE",
                "key": "ORDERS_FK1",
                "key_len": "4",
                "ref": "tpch.customer.C_CUSTKEY",
                "rows": 1,
                "filtered": 44.34,
                "Extra": "Using where"
            },
            {
                "id": 1,
                "select_type": "SIMPLE",
                "table": "lineitem",
                "partitions": None,
                "type": "ref",
                "possible_keys": "LINEITEM_UK1,LINEITEM_FK1,idx_L_ORDERKEY_L_SHIPDATE,idx_L_ORDERKEY_L_SUPPKEY,idx_L_SHIPDATE",
                "key": "LINEITEM_UK1",
                "key_len": "4",
                "ref": "tpch.orders.O_ORDERKEY",
                "rows": 3,
                "filtered": 55.52,
                "Extra": "Using where"
            },
            {
                "id": 2,
                "select_type": "SIMPLE",
                "table": "lineitem",
                "partitions": None,
                "type": "ref",
                "possible_keys": "LINEITEM_UK1,LINEITEM_FK1,idx_L_ORDERKEY_L_SHIPDATE,idx_L_ORDERKEY_L_SUPPKEY,idx_L_SHIPDATE",
                "key": "LINEITEM_UK1",
                "key_len": "4",
                "ref": "tpch.orders.O_ORDERKEY",
                "rows": 30,
                "filtered": 55.52,
                "Extra": "Using where"
            }
        ]
        explain_with_idx_videx_with_gt = [
            {
                "id": 1,
                "select_type": "SIMPLE",
                "table": "ERROR",  # errors
                "partitions": None,
                "type": "ref",
                "possible_keys": "PRIMARY,idx_C_MKTSEGMENT_C_CUSTKEY",
                "key": "ERROR",  # err
                "key_len": "40",
                "ref": "const",
                "rows": 1950,  # err < 0.1
                "filtered": 100.0,
                "Extra": "Using where; "
            },
            {
                "id": 1,
                "select_type": "SIMPLE",
                "table": "orders",
                "partitions": None,
                "type": "ref",
                "possible_keys": "PRIMARY,ORDERS_FK1,idx_O_ORDERKEY_O_ORDERDATE,idx_O_CUSTKEY_O_ORDERKEY_O_ORDERDATE,idx_O_ORDERKEY_O_CUSTKEY_O_ORDERDATE,idx_O_ORDERDATE",
                "key": "ORDERS_FK1",
                "key_len": "4",
                "ref": "tpch.customer.ERROR",  # err
                "rows": 2,
                "filtered": 44.34,
                "Extra": "Using where"
            },
            {
                "id": 1,
                "select_type": "SIMPLE",
                "table": "lineitem",
                "partitions": None,
                "type": "ref",
                "possible_keys": "LINEITEM_UK1,LINEITEM_FK1,idx_L_ORDERKEY_L_SHIPDATE,idx_L_ORDERKEY_L_SUPPKEY,idx_L_SHIPDATE",
                "key": "LINEITEM_UK1",
                "key_len": "4",
                "ref": "tpch.orders.O_ORDERKEY",
                "rows": 30,
                "filtered": 55.52,
                "Extra": "Using where"
            },
            {
                "id": 2,
                "select_type": "SIMPLE",
                "table": "lineitem",
                "partitions": None,
                "type": "ref",
                "possible_keys": "LINEITEM_UK1,LINEITEM_FK1,idx_L_ORDERKEY_L_SHIPDATE,idx_L_ORDERKEY_L_SUPPKEY,idx_L_SHIPDATE",
                "key": "LINEITEM_UK1",
                "key_len": "4",
                "ref": "tpch.orders.O_ORDERKEY",
                "rows": 30,
                "filtered": 55.52,
                "Extra": "Using where"
            }
        ]
        res = compare_explain(expect=explain_with_idx_innodb, actual=explain_with_idx_videx_with_gt)
        print(res)
        expect_res = {'score': 0.25,
                      'msg': 'item=0, id=1, actual: table=ERROR, expected: table=customer',
                      'diff': {
                          0: {'table': {'expected': 'customer', 'actual': 'ERROR'},
                              'key': {'expected': 'idx_C_MKTSEGMENT_C_CUSTKEY', 'actual': 'ERROR'}},
                          1: {'ref': {'expected': 'tpch.customer.C_CUSTKEY', 'actual': 'tpch.customer.ERROR'}},
                          2: {'rows': {'expected': 3.0, 'actual': 30.0}}}}

        # self.assertDictEqual({'score': 1.0, 'msg': '', 'diff': {}}, res)
        self.assertAlmostEquals(expect_res['score'], res['score'])
        self.assertEqual(expect_res['msg'], res['msg'])
        self.assertDictEqual(expect_res['diff'], res['diff'])

    def test_check_videx_trace(self):
        result = load_json_from_file(
            os.path.join(os.path.dirname(__file__),
                         'data/test_videx_trace_check.json'))
        success_list, failed_list = search_videx_http_dict(result['trace_wo_idx_videx_with_gt'])
        expect_success = [
            {'dict_name': 'videx_http', 'url': 'http://127.0.0.1:5001/ask_videx',
             'request': '{"item_type":"videx_request","properties":{"dbname":"videx_tpch","function":"virtual int ha_videx::info_low(uint, bool)","table_name":"orders","target_storage_engine":"INNODB","videx_options":"{\\"task_id\\": \\"127_0_0_1_13308@@@demo_tpch\\", \\"use_gt\\": true}"},"data":[{"item_type":"key","properties":{"key_length":"4","name":"PRIMARY"},"data":[{"item_type":"field","properties":{"name":"O_ORDERKEY","store_length":"4"},"data":[]}]},{"item_type":"key","properties":{"key_length":"4","name":"ORDERS_FK1"},"data":[{"item_type":"field","properties":{"name":"O_CUSTKEY","store_length":"4"},"data":[]},{"item_type":"field","properties":{"name":"O_ORDERKEY","store_length":"4"},"data":[]}]}]}',
             'success': True,
             'detail': '{\n  "code": 200, \n  "data": {\n    "ORDERS_FK1 #@# O_CUSTKEY": "15.14957685096032", \n    "ORDERS_FK1 #@# O_ORDERKEY": "1.0147397762828907", \n    "PRIMARY #@# O_ORDERKEY": "1.0", \n    "data_file_length": "202047488", \n    "data_free_length": "4194304", \n    "index_file_length": "39403520", \n    "stat_clustered_index_size": "12332", \n    "stat_n_rows": "1494733", \n    "stat_sum_of_other_index_sizes": "2405"\n  }, \n  "message": "OK"\n}\n'}]
        expect_failed = [
            {'dict_name': 'videx_http', 'url': 'http://127.0.0.1:5001/ask_videx',
             'request': '{"item_type":"videx_request","properties":{"dbname":"videx_tpch","function":"virtual double ha_videx::scan_time()","table_name":"region","target_storage_engine":"INNODB","videx_options":"{\\"task_id\\": \\"127_0_0_1_13308@@@demo_tpch\\", \\"use_gt\\": true}"},"data":[]}',
             'success': False, 'reason': 'res_code != CURLE_OK',
             'detail': 'A libcurl function was given a bad argument'}]
        print(success_list, failed_list)
        self.assertListEqual(expect_success, success_list)
        self.assertListEqual(expect_failed, failed_list)
        # print(success_list, failed_list)
        success_list, failed_list = search_videx_http_dict(result['trace_wo_idx_videx_wo_gt'])

        expect_success = [
            {'dict_name': 'videx_http', 'url': 'http://127.0.0.1:5001/ask_videx',
             'request': '{"item_type":"videx_request","properties":{"dbname":"videx_tpch","function":"virtual double ha_videx::scan_time()","table_name":"lineitem","target_storage_engine":"INNODB","videx_options":"{\\"task_id\\": \\"127_0_0_1_13308@@@demo_tpch\\", \\"use_gt\\": false}"},"data":[]}',
             'success': True,
             'detail': '{\n  "code": 200, \n  "data": {\n    "value": "56640"\n  }, \n  "message": "OK"\n}\n'}]
        expect_failed = [
            {'dict_name': 'videx_http', 'url': 'http://127.0.0.1:5001/ask_videx',
             'request': '{"item_type":"videx_request","properties":{"dbname":"videx_tpch","function":"virtual double ha_videx::scan_time()","table_name":"region","target_storage_engine":"INNODB","videx_options":"{\\"task_id\\": \\"127_0_0_1_13308@@@demo_tpch\\", \\"use_gt\\": true}"},"data":[]}',
             'success': False, 'reason': 'res_code != CURLE_OK',
             'detail': 'A libcurl function was given a bad argument'}]
        print(success_list, failed_list)
        self.assertListEqual(expect_success, success_list)
        self.assertListEqual(expect_failed, failed_list)


class TestConstructInvolvedDbTables(unittest.TestCase):
    def test_empty_input(self):
        result = construct_involved_db_tables([])
        self.assertEqual(result, {})

    def test_single_table_id_set(self):
        table_id_set = {TableId(db_name='db1', table_name='table1')}
        expected = {'db1': ['table1']}
        result = construct_involved_db_tables([table_id_set])
        self.assertEqual(result, expected)

    def test_multiple_table_id_sets_with_duplicates(self):
        table_id_set1 = {TableId(db_name='db1', table_name='table1'), TableId(db_name='db1', table_name='table2')}
        table_id_set2 = {TableId(db_name='db1', table_name='table2'), TableId(db_name='db1', table_name='table3')}
        expected = {'db1': ['table1', 'table2', 'table3']}
        result = construct_involved_db_tables([table_id_set1, table_id_set2])
        self.assertEqual(result, expected)

    def test_multiple_table_id_sets_with_different_databases(self):
        table_id_set1 = {TableId(db_name='db1', table_name='table1'), TableId(db_name='db1', table_name='table2')}
        table_id_set2 = {TableId(db_name='db2', table_name='table3'), TableId(db_name='db2', table_name='table4')}
        expected = {'db1': ['table1', 'table2'], 'db2': ['table3', 'table4']}
        result = construct_involved_db_tables([table_id_set1, table_id_set2])
        self.assertEqual(result, expected)

    def test_sorted_output(self):
        table_id_set1 = {TableId(db_name='db1', table_name='table2'), TableId(db_name='db1', table_name='table1')}
        table_id_set2 = {TableId(db_name='db2', table_name='table4'), TableId(db_name='db2', table_name='table3')}
        expected = {'db1': ['table1', 'table2'], 'db2': ['table3', 'table4']}
        result = construct_involved_db_tables([table_id_set1, table_id_set2])
        self.assertEqual(result, expected)

    def test_duplicate_elements(self):
        table_id_set1 = {TableId(db_name='db1', table_name='table2'), TableId(db_name='db2', table_name='table1')}
        table_id_set2 = {TableId(db_name='db2', table_name='table3'), TableId(db_name='db2', table_name='table1')}
        expected = {'db1': ['table2'], 'db2': ['table1', 'table3']}
        result = construct_involved_db_tables([table_id_set1, table_id_set2])
        self.assertEqual(expected, result)


class TestParseDatetime(unittest.TestCase):

    def test_date_format(self):
        self.assertEqual(parse_datetime("2023-01-01"), datetime(2023, 1, 1))

    def test_datetime_format(self):
        self.assertEqual(parse_datetime("2023-01-01 12:00:00"), datetime(2023, 1, 1, 12, 0))

    def test_datetime_format_with_microseconds(self):
        self.assertEqual(parse_datetime("2023-01-01 12:00:00.123456"), datetime(2023, 1, 1, 12, 0, 0, 123456))

    def test_quoted_datetime_format(self):
        self.assertEqual(parse_datetime("'2023-01-01 12:00:00'"), datetime(2023, 1, 1, 12, 0))

    def test_quoted_datetime_format_with_microseconds(self):
        self.assertEqual(parse_datetime('"2023-01-01 12:00:00.123456"'), datetime(2023, 1, 1, 12, 0, 0, 123456))

    def test_int_timestamp_seconds(self):
        self.assertEqual(parse_datetime(1640995200), datetime.fromtimestamp(1640995200))

    def test_int_timestamp_milliseconds(self):
        self.assertEqual(parse_datetime(1640995200000), datetime.fromtimestamp(1640995200))

    def test_int_timestamp_microseconds(self):
        self.assertEqual(parse_datetime(1640995200000000), datetime.fromtimestamp(1640995200))

    def test_int_timestamp_nanoseconds(self):
        self.assertEqual(parse_datetime(1640995200000000000), datetime.fromtimestamp(1640995200))

    def test_str_timestamp_nanoseconds(self):
        self.assertEqual(parse_datetime("1104742802000000000"), datetime.fromtimestamp(1104742802))
        # datetime 微秒以下的会被丢掉
        expect_str = datetime.strftime(datetime.fromtimestamp(1104742802), '%Y-%m-%d %H:%M:%S.%f')
        self.assertEqual(reformat_datetime_str("1104742802000000999"), expect_str)

    def test_invalid_input(self):
        with self.assertRaises(ValueError):
            parse_datetime("Not a date")

    def test_invalid_integer_length(self):
        with self.assertRaises(ValueError):
            parse_datetime(1640995200000000000000)  # Too long to be a valid timestamp

    def test_non_string_non_int_input(self):
        with self.assertRaises(ValueError):
            parse_datetime([])  # Input is neither a string nor an integer

    def test_reformat_datetime_str(self):
        expect_str = datetime.strftime(datetime.fromtimestamp(1104742802).replace(microsecond=123),
                                       '%Y-%m-%d %H:%M:%S.%f')
        self.assertEqual(reformat_datetime_str("1104742802000123000"), expect_str)
        expect_str = datetime.strftime(datetime.fromtimestamp(1104742802).replace(microsecond=851209),
                                       '%Y-%m-%d %H:%M:%S.%f')
        self.assertEqual(reformat_datetime_str("1104742802851209"), expect_str)

    def test_is_datetime_like(self):
        """Test various datetime types with pandas type checking functions."""

        # Create series with different datetime-related types
        series_list = [
            # Standard datetime64 series
            pd.Series(pd.date_range('2023-01-01', periods=3)),

            # Series created from Python datetime objects
            pd.Series([datetime(2023, 1, 1), datetime(2023, 1, 2)]),

            # Series created from date objects
            pd.Series([date(2023, 1, 1), date(2023, 1, 2)]),

            # String dates converted to datetime
            pd.Series(['2023-01-01', '2023-01-02']).astype('datetime64[ns]'),

            # NumPy datetime64 type
            pd.Series(np.array(['2023-01-01', '2023-01-02'], dtype='datetime64')),

            # Timezone-aware datetime
            pd.Series(pd.date_range('2023-01-01', periods=3, tz='UTC')),

            # Period type
            pd.Series(pd.period_range('2023-01', periods=3, freq='M')),
        ]

        # Non-datetime types for comparison
        non_datetime_series = [
            pd.Series([1, 2, 3]),
            pd.Series(['a', 'b', 'c']),
            pd.Series([1, 2, 3], dtype='Int32'),
        ]

        # Test each datetime series
        for i, s in enumerate(series_list):
            print(f"\nTest {i+1}:")
            print(f"Series: {s}")
            print(f"Series dtype: {s.dtype}")
            if str(s.dtype) == 'object':
                print()

            # Check that is_datetime64_any_dtype correctly identifies datetime types
            self.assertTrue(is_datetime_like(s), f"Failed to identify datetime type: {s.dtype}")

            # Print results of other datetime type check functions
            print(f"is_datetime64_any_dtype result: {pd.api.types.is_datetime64_any_dtype(s)}")
            print(f"is_datetime64_dtype result: {pd.api.types.is_datetime64_dtype(s)}")
            print(f"is_datetime64_ns_dtype result: {pd.api.types.is_datetime64_ns_dtype(s)}")
            print(f"is_period_dtype result: {pd.api.types.is_period_dtype(s)}")

        # Test that non-datetime types are correctly identified
        for i, s in enumerate(non_datetime_series):
            print(f"\nNon-datetime Test {i+1}:")
            print(f"Series: {s}")
            print(f"Series dtype: {s.dtype}")

            # Check that is_datetime64_any_dtype correctly rejects non-datetime types
            self.assertFalse(is_datetime_like(s),
                             f"Incorrectly identified non-datetime type as datetime: {s.dtype}"
                             )

            # Print results of datetime type check functions on non-datetime types
            print(f"is_datetime64_any_dtype result: {pd.api.types.is_datetime64_any_dtype(s)}")
            print(f"is_datetime64_dtype result: {pd.api.types.is_datetime64_dtype(s)}")
            print(f"is_datetime64_ns_dtype result: {pd.api.types.is_datetime64_ns_dtype(s)}")
            print(f"is_period_dtype result: {pd.api.types.is_period_dtype(s)}")


if __name__ == '__main__':
    pass
