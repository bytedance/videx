# -*- coding: utf-8 -*-
"""
TODO: add file description.

@ author: kangrong
@ date: 2023/11/17 
"""
import json
import os
import unittest
from typing import List

from sub_platforms.sql_opt.videx.videx_histogram import HistogramBucket, HistogramStats, init_bucket_by_type
from sub_platforms.sql_opt.videx.videx_service import VidexSingleton
from sub_platforms.sql_opt.videx.videx_utils import IndexRangeCond, GT_Table_Return, load_json_from_file, \
    BTreeKeyOp, BTreeKeySide


class TestHist_find_first_key_pos(unittest.TestCase):
    """
    下面是 tpcc ITEM 的 explain 到底层条件的例子，用于配合理解 test 的正确性
    """

    def setUp(self):
        # 2 和 3 有间隔
        bucket1 = HistogramBucket(min_value=1, max_value=3, cum_freq=0.6, row_count=60)
        # 3的上下界一样
        bucket2 = HistogramBucket(min_value=4, max_value=4, cum_freq=0.8, row_count=20)
        # 最大到 4
        bucket3 = HistogramBucket(min_value=5, max_value=6, cum_freq=1, row_count=20)
        self.int_table_rows = 100
        self.int_histogram = HistogramStats(
            buckets=[bucket1, bucket2, bucket3],
            data_type="int", null_values=0.1, collation_id=1, last_updated="2023-11-19",
            sampling_rate=0.8, histogram_type="basic", number_of_buckets_specified=3)

        self.float_table_rows = 100
        self.float_histogram = HistogramStats(
            buckets=[bucket1, bucket2, bucket3],
            data_type="float", null_values=0.1, collation_id=1, last_updated="2023-11-19",
            sampling_rate=0.8, histogram_type="basic", number_of_buckets_specified=3)

        str_bucket_list = {
            "buckets": [
                {
                    "min_value": "base64:type254:YXhhaGtyc2I=",
                    "max_value": "base64:type254:ZHZ1bXV1eWVh",
                    "cum_freq": 0.1,
                    "row_count": 8
                },
                {
                    "min_value": "base64:type254:ZHltb2p3bW94",
                    "max_value": "base64:type254:ZnBtZmty",
                    "cum_freq": 0.2,
                    "row_count": 8
                },
                {
                    "min_value": "base64:type254:ZnR1cXY=",
                    "max_value": "base64:type254:aGN2Ympx",
                    "cum_freq": 0.3,
                    "row_count": 8
                },
                {
                    "min_value": "base64:type254:aGpqY2JxcQ==",
                    "max_value": "base64:type254:aXlkd3Fk",
                    "cum_freq": 0.4,
                    "row_count": 8
                },
                {
                    "min_value": "base64:type254:aXlld21tdg==",
                    "max_value": "base64:type254:bHdvdmZi",
                    "cum_freq": 0.5,
                    "row_count": 8
                },
                {
                    "min_value": "base64:type254:bHl2ZmVi",
                    "max_value": "base64:type254:cWxoemxjd3c=",
                    "cum_freq": 0.6,
                    "row_count": 8
                },
                {
                    "min_value": "base64:type254:cXh2ZXJm",
                    "max_value": "base64:type254:c3lwaGQ=",
                    "cum_freq": 0.7,
                    "row_count": 8
                },
                {
                    "min_value": "base64:type254:dGlmdW1lYQ==",
                    "max_value": "base64:type254:dWJ0cmN2Zng=",
                    "cum_freq": 0.8,
                    "row_count": 8
                },
                {
                    "min_value": "base64:type254:dWZlcGhhZ3Nm",
                    "max_value": "base64:type254:eHdlYW5ma3A=",
                    "cum_freq": 0.9,
                    "row_count": 8
                },
                {
                    "min_value": "base64:type254:eHlmdnZubXc=",
                    "max_value": "base64:type254:emd6em5q",
                    "cum_freq": 1,
                    "row_count": 8
                }
            ],
            "data_type": "string",
            "null_values": 0,
            "collation_id": 8,
            "last_updated": "2023-11-19 03:04:12.606021",
            "sampling_rate": 1,
            "histogram_type": "equi-height",
            "number_of_buckets_specified": 10
        }
        str_buckets: List[HistogramBucket] = []
        data_type = "string"
        histogram_type = "equi-height"
        for bucket_raw in str_bucket_list["buckets"]:
            bucket = init_bucket_by_type(list(bucket_raw.values()), data_type, histogram_type)
            str_buckets.append(bucket)
        self.string_table_rows = 80
        self.string_histogram = HistogramStats(
            buckets=str_buckets,
            data_type=data_type, null_values=0.1, collation_id=1, last_updated="2023-11-19",
            sampling_rate=0.8, histogram_type=histogram_type, number_of_buckets_specified=3)

    def test_find_in_histogram(self):
        # 使用示例
        function1 = BTreeKeyOp.init("HA_READ_KEY_EXACT")
        print(function1)  # 输出 HaRKeyFunction.HA_READ_KEY_EXACT
        self.assertEqual(function1, BTreeKeyOp.EQ)
        function2 = BTreeKeyOp.init("=")
        print(function2)  # 输出 HaRKeyFunction.HA_READ_KEY_EXACT
        self.assertEqual(function2, BTreeKeyOp.EQ)
        function3 = BTreeKeyOp.init("EQ")
        print(function3)  # 输出 HaRKeyFunction.HA_READ_KEY_EXACT
        self.assertEqual(function3, BTreeKeyOp.EQ)

    def test_gt_operator(self):
        """
        EXPLAIN select I_PRICE from ITEM where I_PRICE = 12
        - `MIN_KEY: {I_PRICE_____=_____12.00}, MAX_KEY: {I_PRICE_____>_____12.00}`

        EXPLAIN select I_PRICE from ITEM where I_PRICE > 12
        - `{MIN_KEY: {I_PRICE_____>_____12.00}, MAX_KEY: {<NO_KEY_RANGE>}}`

        EXPLAIN select I_PRICE from ITEM where I_PRICE <= 12
        - `{MIN_KEY: {<NO_KEY_RANGE>}, MAX_KEY: {I_PRICE_____>_____12.00}}`

        """
        op = BTreeKeyOp.GT
        op = BTreeKeySide.from_op(op)
        self.assertEqual(self.int_histogram.find_nearest_key_pos(0, op) * self.int_table_rows, 0)
        self.assertEqual(self.int_histogram.find_nearest_key_pos(1, op) * self.int_table_rows, 20)
        self.assertEqual(self.int_histogram.find_nearest_key_pos(2, op) * self.int_table_rows, 40)
        self.assertEqual(self.int_histogram.find_nearest_key_pos(4, op) * self.int_table_rows, 80)
        self.assertEqual(self.int_histogram.find_nearest_key_pos(5, op) * self.int_table_rows, 90)
        self.assertEqual(self.int_histogram.find_nearest_key_pos(6, op) * self.int_table_rows, 100)
        self.assertEqual(self.int_histogram.find_nearest_key_pos(10, op) * self.int_table_rows, 100)

    def test_eq_operator(self):
        """
        EXPLAIN select I_PRICE from ITEM where I_PRICE = 12
        - `MIN_KEY: {I_PRICE_____=_____12.00}, MAX_KEY: {I_PRICE_____>_____12.00}`

        EXPLAIN select I_PRICE from ITEM where I_PRICE >= 12
        - `{MIN_KEY: {I_PRICE_____=_____12}, MAX_KEY: {<NO_KEY_RANGE>}}`

        """
        op = BTreeKeyOp.EQ
        op = BTreeKeySide.from_op(op)
        # 所有 bucket 都大于 0，因此结果为 0
        self.assertEqual(self.int_histogram.find_nearest_key_pos(0, op) * self.int_table_rows, 0)
        # 命中第一个 bucket，但等于左边界。1左边没有值
        self.assertEqual(self.int_histogram.find_nearest_key_pos(1, op) * self.int_table_rows, 0)
        # =2，左边只有 1。1 所占比例是 1/3
        self.assertEqual(self.int_histogram.find_nearest_key_pos(2, op) * self.int_table_rows, 20)
        # 按照均匀假设，一个值至少占 1/rpw_count=1/60，
        # 又因为是 int，所以一个值至少占 1/ (max-min+1)=1/3，
        # 3 占了1/3，3 左边有2/3
        # 综上占 =3 左边有 100 * 0.6 * 2/3=40
        self.assertEqual(self.int_histogram.find_nearest_key_pos(3, op) * self.int_table_rows, 40)
        # 第一个 bucket 全占，不包含第二个，因此是 60
        self.assertEqual(self.int_histogram.find_nearest_key_pos(4, op) * self.int_table_rows, 60)
        # 前两个全占
        self.assertEqual(self.int_histogram.find_nearest_key_pos(5, op) * self.int_table_rows, 80)
        # 第三个全占，100 个
        self.assertEqual(self.int_histogram.find_nearest_key_pos(6, op) * self.int_table_rows, 90)
        # 第三个全占，100 个
        self.assertEqual(self.int_histogram.find_nearest_key_pos(10, op) * self.int_table_rows, 100)

    def test_lt_operator(self):
        """
        `EXPLAIN select I_PRICE from ITEM where I_PRICE < 12`
         - `MIN_KEY: {<NO_KEY_RANGE>}, MAX_KEY: {I_PRICE_____<_____12.00}}`
        和 EQ 合并
        """
        pass
        # op = BTreeKeyOp.LT
        # # 0- 左边没有值
        # self.assertEqual(self.histogram.find_nearest_key_pos(0, op), 0)
        # # 1- 不含有 bucket，所以是 0
        # self.assertEqual(self.histogram.find_nearest_key_pos(1, op), 0)
        # # 2- 即 1
        #
        # # 如果按照均匀假设，2- 就是 1
        #
        # self.assertEqual(self.histogram.find_nearest_key_pos(2, op), 20)
        # # 4-就是第一个 bucket，排除第二个 bucket
        # self.assertEqual(self.histogram.find_nearest_key_pos(4, op), 60)
        #
        # self.assertEqual(self.histogram.find_nearest_key_pos(5, op), 60)
        # # 6-就是 5
        # self.assertEqual(self.histogram.find_nearest_key_pos(6, op), 90)
        # # 第三个全占，100 个
        # self.assertEqual(self.histogram.find_nearest_key_pos(10, op), 100)

    def test_float_operator(self):
        op = BTreeKeyOp.GT
        op = BTreeKeySide.from_op(op)
        self.assertEqual(self.float_histogram.find_nearest_key_pos(0, op) * self.float_table_rows, 0)
        # int to float，20 -> 1，因为从 1~3不能再假设是 1/3 了
        self.assertEqual(self.float_histogram.find_nearest_key_pos(1, op) * self.float_table_rows, 1)
        # 1~2，2~3，所以 2 正好在这一段的 50% 处
        self.assertEqual(self.float_histogram.find_nearest_key_pos(2, op) * self.float_table_rows, 31)
        self.assertEqual(self.float_histogram.find_nearest_key_pos(4, op) * self.float_table_rows, 80)
        self.assertEqual(self.float_histogram.find_nearest_key_pos(5, op) * self.float_table_rows, 81)
        # 6 是右边界，所以全部 bucket 都囊括了
        self.assertEqual(self.float_histogram.find_nearest_key_pos(6, op) * self.float_table_rows, 100)
        self.assertEqual(self.float_histogram.find_nearest_key_pos(10, op) * self.float_table_rows, 100)

        op = BTreeKeyOp.EQ
        op = BTreeKeySide.from_op(op)
        self.assertEqual(self.float_histogram.find_nearest_key_pos(0, op) * self.float_table_rows, 0)
        self.assertEqual(self.float_histogram.find_nearest_key_pos(1, op) * self.float_table_rows, 0)
        self.assertEqual(self.float_histogram.find_nearest_key_pos(2, op) * self.float_table_rows, 30)
        # 3 是 bucket 1 的右边界，所以左边应该有 60 个数据，但 3至少占 1 个，所以左边 59 rows
        self.assertEqual(self.float_histogram.find_nearest_key_pos(3, op) * self.float_table_rows, 59)
        # 4 ，恰好不沾惹 bucket 2
        self.assertEqual(self.float_histogram.find_nearest_key_pos(4, op) * self.float_table_rows, 60)
        #
        self.assertEqual(self.float_histogram.find_nearest_key_pos(5, op) * self.float_table_rows, 80)
        self.assertEqual(self.float_histogram.find_nearest_key_pos(6, op) * self.float_table_rows, 99)
        self.assertEqual(self.float_histogram.find_nearest_key_pos(10, op) * self.float_table_rows, 100)

    def test_string_operator(self):
        # "D_NAME"

        """
        python 和 InnoDB 的结论一样。两个字符串如果前缀相同，则longer> shorter，
        例如 'axa' > 'axah' => True
        前缀不同，则由前缀决定，例如 'axb' > 'axa'  => True  
        这和 sql 一样的
        
        当前 D_NAME 是 DISTRICT 的，类型为 `D_NAME` varchar(10)，所以解码之后所有字符都是10 位，下面是 bucket：
        
        select D_NAME from `DISTRICT` where `D_NAME` <= 'dvumuuyea' and `D_NAME` >= 'axahkrsb' order by `D_NAME`
        +-----------+
        | D_NAME    |
        |-----------|
        | axahkrsb  |
        | aymwo     |
        | bkogaixe  |
        | bqqmc     |
        | brrux     |
        | cdamkdb   |
        | csrkyjfzd |
        | dvumuuyea |
        +-----------+
        """
        op = BTreeKeyOp.EQ
        op = BTreeKeySide.from_op(op)
        self.assertEqual(self.string_histogram.find_nearest_key_pos('ax', op) * self.string_table_rows, 0)
        # axahkrsb 明确是 min，所以知道他在最左边
        self.assertEqual(self.string_histogram.find_nearest_key_pos('axahkrsb', op) * self.string_table_rows, 0)
        # 暂定为bucket 中的字符串就占一半，每个 bucket 都是 8 行，因此是 4
        self.assertEqual(self.string_histogram.find_nearest_key_pos('bqqmc', op) * self.string_table_rows, 4)
        # 明确知道是 max，所以在最右边
        self.assertAlmostEquals(self.string_histogram.find_nearest_key_pos('dvumuuyea', op) * self.string_table_rows, 7)
        # 被归并到 bucket[0].max了，其实差了一行
        self.assertAlmostEquals(self.string_histogram.find_nearest_key_pos('dvumuuyea_', op) * self.string_table_rows, 7)

        op = BTreeKeyOp.GT
        op = BTreeKeySide.from_op(op)
        self.assertEqual(self.string_histogram.find_nearest_key_pos('ax', op) * self.string_table_rows, 0)
        # 暂定为bucket 中的字符串就占一半，每个 bucket 都是 8 行，因此是 4
        # TODO 这个不一定合理。假如bucket= ['a','c','d']，条件是'b'，根本没出现在 bucket 中，凭什么认定他的宽度至少为 1？
        #  但是先不管了
        self.assertEqual(self.string_histogram.find_nearest_key_pos('ax', op) * self.string_table_rows, 0)
        self.assertEqual(self.string_histogram.find_nearest_key_pos('axahkrsb', op) * self.string_table_rows, 1)
        self.assertEqual(self.string_histogram.find_nearest_key_pos('bqqmc', op) * self.string_table_rows, 5)
        self.assertEqual(self.string_histogram.find_nearest_key_pos('dvumuuyea', op) * self.string_table_rows, 8)


class Test_record_in_ranges_algorithm(unittest.TestCase):
    def setUp(self):
        # 替换 ITEM 的 histogram，便于测试。测试范围是 I_PRICE、I_IM_ID
        hist_dict = {
                'ITEM': {
                    "I_PRICE": HistogramStats(

                        buckets=[
                            HistogramBucket(min_value=1, max_value=3, cum_freq=0.6, row_count=60),
                            HistogramBucket(min_value=4, max_value=4, cum_freq=0.8, row_count=20),
                            HistogramBucket(min_value=5, max_value=6, cum_freq=1, row_count=20)
                        ],
                        data_type="decimal", null_values=0.1, collation_id=1, last_updated="2023-11-19",
                        sampling_rate=0.8, histogram_type="basic", number_of_buckets_specified=3),
                    "I_IM_ID": HistogramStats(
                        buckets=[
                            HistogramBucket(min_value=1, max_value=1, cum_freq=0.25, row_count=1),
                            HistogramBucket(min_value=2, max_value=2, cum_freq=0.5, row_count=1),
                            HistogramBucket(min_value=3, max_value=3, cum_freq=0.75, row_count=1),
                            HistogramBucket(min_value=4, max_value=4, cum_freq=1, row_count=1),
                        ],
                        data_type="int", null_values=0.1, collation_id=1, last_updated="2023-11-19",
                        sampling_rate=0.8, histogram_type="basic", number_of_buckets_specified=3)
                }
            }
        self.raw_db = 'tpcc'
        self.videx_db = 'videx_tpcc'
        self.task_id = 'test_rr_tpcc'
        stats_dict = load_json_from_file(
                    os.path.join(os.path.dirname(__file__),
                                 "data/test_videx_meta_record_in_ranges_tpcc.json"))
        stats_dict['ITEM']['TABLE_ROWS'] = 100
        self.singleton = VidexSingleton()
        # 在这个测试例中，我们只需要传入的空 ndv，因为测试例仅测试 records_in_range，不会用到ndv_single_file
        ndv_single_file = {tb: {} for tb in stats_dict}
        for tb in stats_dict:
            if tb not in hist_dict:
                hist_dict[tb] = {}
        self.singleton.add_task_meta_from_local_files(
                task_id=self.task_id,
                raw_db=self.raw_db,
                videx_db=self.videx_db,
                stats_file=stats_dict,
                hist_file=hist_dict,
                ndv_single_file=ndv_single_file,
                ndv_mulcol_file=None,
                gt_rec_in_ranges_file=None,
                gt_req_resp_file=None,
        )

    def test_single_eq(self):
        req_json = {'item_type': 'videx_request',
                    'properties': {'dbname': 'tpcc',
                                   'function': 'virtual ha_rows ha_videx::records_in_range(uint, key_range*, key_range*)',
                                   'table_name': 'ITEM', 'target_storage_engine': 'INNODB'},
                    "data": [{"item_type": "min_key", "properties": {"index_name": "idx_I_PRICE_I_IM_ID", "length": "3",
                                                                     "operator": "="},
                              "data": [{"item_type": "column_and_bound",
                                        "properties": {"column": "I_PRICE", "value": "3.00"}, "data": []}]},
                             {"item_type": "max_key", "properties": {"index_name": "idx_I_PRICE_I_IM_ID", "length": "3",
                                                                     "operator": ">"},
                              "data": [{"item_type": "column_and_bound",
                                        "properties": {"column": "I_PRICE", "value": "3.00"}, "data": []}]}]}

        req_json['properties']['dbname'] = self.videx_db
        req_json['properties']["videx_options"] = json.dumps({
            "task_id": self.task_id,
            "use_gt": False
        })
        res = self.singleton.ask(
            req_json_item=req_json,
            raise_out=True
        )
        print(res)
        self.assertEqual(res, (200, 'OK', {'value': '1'}))

    def test_single_eq_int(self):
        # EXPLAIN select I_PRICE from ITEM where I_IM_ID = 3
        # KEY: idx_I_IM_ID   MIN_KEY: { =  I_IM_ID(3), }, MAX_KEY: { >  I_IM_ID(3), }
        req_json = {"item_type": "videx_request", "properties": {"dbname": "tpcc",
                                                                 "function": "virtual ha_rows ha_innobase::records_in_range(uint, key_range*, key_range*)",
                                                                 "table_name": "ITEM",
                                                                 "target_storage_engine": "INNODB"}, "data": [
            {"item_type": "min_key", "properties": {"index_name": "idx_I_IM_ID", "length": "4", "operator": "="},
             "data": [
                 {"item_type": "column_and_bound", "properties": {"column": "I_IM_ID", "value": "3"}, "data": []}]},
            {"item_type": "max_key", "properties": {"index_name": "idx_I_IM_ID", "length": "4", "operator": ">"},
             "data": [
                 {"item_type": "column_and_bound", "properties": {"column": "I_IM_ID", "value": "3"}, "data": []}]}]}

        req_json['properties']['dbname'] = self.videx_db
        req_json['properties']["videx_options"] = json.dumps({
            "task_id": self.task_id,
            "use_gt": False
        })
        res = self.singleton.ask(
            req_json_item=req_json,
            raise_out=True
        )
        print(res)
        self.assertEqual(res, (200, 'OK', {'value': '25'}))

    def test_single_lte(self):
        # EXPLAIN select I_PRICE from ITEM where I_IM_ID <= 3
        req_json = {"item_type": "videx_request", "properties": {"dbname": "tpcc",
                                                                 "function": "virtual ha_rows ha_innobase::records_in_range(uint, key_range*, key_range*)",
                                                                 "table_name": "ITEM",
                                                                 "target_storage_engine": "INNODB"},
                    "data": [{"item_type": "min_key", "properties": {}, "data": []}, {"item_type": "max_key",
                                                                                      "properties": {
                                                                                          "index_name": "idx_I_IM_ID",
                                                                                          "length": "4",
                                                                                          "operator": ">"}, "data": [
                            {"item_type": "column_and_bound", "properties": {"column": "I_IM_ID", "value": "3"},
                             "data": []}]}]}

        req_json['properties']['dbname'] = self.videx_db
        req_json['properties']["videx_options"] = json.dumps({
            "task_id": self.task_id,
            "use_gt": False
        })
        res = self.singleton.ask(
            req_json_item=req_json,
            raise_out=True
        )
        print(res)
        self.assertEqual(res, (200, 'OK', {'value': '75'}))

    def test_single_lt(self):
        # EXPLAIN select I_PRICE from ITEM where I_IM_ID <= 3
        # KEY: idx_I_IM_ID   MIN_KEY: {<NO_KEY_RANGE>}, MAX_KEY: { <  I_IM_ID(3), }
        req_json = {"item_type": "videx_request", "properties": {"dbname": "tpcc",
                                                                 "function": "virtual ha_rows ha_innobase::records_in_range(uint, key_range*, key_range*)",
                                                                 "table_name": "ITEM",
                                                                 "target_storage_engine": "INNODB"},
                    "data": [{"item_type": "min_key", "properties": {}, "data": []}, {"item_type": "max_key",
                                                                                      "properties": {
                                                                                          "index_name": "idx_I_IM_ID",
                                                                                          "length": "4",
                                                                                          "operator": "<"}, "data": [
                            {"item_type": "column_and_bound", "properties": {"column": "I_IM_ID", "value": "3"},
                             "data": []}]}]}

        req_json['properties']['dbname'] = self.videx_db
        req_json['properties']["videx_options"] = json.dumps({
            "task_id": self.task_id,
            "use_gt": False
        })
        res = self.singleton.ask(
            req_json_item=req_json,
            raise_out=True
        )
        print(res)
        self.assertEqual(res, (200, 'OK', {'value': '50'}))

    def test_single_gt(self):
        # EXPLAIN select I_PRICE from ITEM where I_IM_ID > 3
        # KEY: idx_I_IM_ID   MIN_KEY: { >  I_IM_ID(3), }, MAX_KEY: {<NO_KEY_RANGE>}
        req_json = {"item_type": "videx_request", "properties": {"dbname": "tpcc",
                                                                 "function": "virtual ha_rows ha_innobase::records_in_range(uint, key_range*, key_range*)",
                                                                 "table_name": "ITEM",
                                                                 "target_storage_engine": "INNODB"}, "data": [
            {"item_type": "min_key", "properties": {"index_name": "idx_I_IM_ID", "length": "4", "operator": ">"},
             "data": [
                 {"item_type": "column_and_bound", "properties": {"column": "I_IM_ID", "value": "3"}, "data": []}]},
            {"item_type": "max_key", "properties": {}, "data": []}]}

        req_json['properties']['dbname'] = self.videx_db
        req_json['properties']["videx_options"] = json.dumps({
            "task_id": self.task_id,
            "use_gt": False
        })
        res = self.singleton.ask(
            req_json_item=req_json,
            raise_out=True
        )
        print(res)
        self.assertEqual(res, (200, 'OK', {'value': '25'}))

    def test_single_gte(self):
        # EXPLAIN select I_PRICE from ITEM where I_IM_ID >= 3
        # KEY: idx_I_IM_ID   MIN_KEY: { =  I_IM_ID(3), }, MAX_KEY: {<NO_KEY_RANGE>}
        req_json = {"item_type": "videx_request", "properties": {"dbname": "tpcc",
                                                                 "function": "virtual ha_rows ha_innobase::records_in_range(uint, key_range*, key_range*)",
                                                                 "table_name": "ITEM",
                                                                 "target_storage_engine": "INNODB"}, "data": [
            {"item_type": "min_key", "properties": {"index_name": "idx_I_IM_ID", "length": "4", "operator": "="},
             "data": [
                 {"item_type": "column_and_bound", "properties": {"column": "I_IM_ID", "value": "3"}, "data": []}]},
            {"item_type": "max_key", "properties": {}, "data": []}]}

        req_json['properties']['dbname'] = self.videx_db
        req_json['properties']["videx_options"] = json.dumps({
            "task_id": self.task_id,
            "use_gt": False
        })
        res = self.singleton.ask(
            req_json_item=req_json,
            raise_out=True
        )
        print(res)
        self.assertEqual(res, (200, 'OK', {'value': '50'}))

    def test_single_gte_le(self):
        # EXPLAIN select I_PRICE from ITEM where I_PRICE > 2 and I_PRICE <= 4
        # KEY: idx_I_PRICE   MIN_KEY: { >  I_PRICE(2.00), }, MAX_KEY: { >  I_PRICE(4.00), }
        req_json = {"item_type": "videx_request", "properties": {"dbname": "tpcc",
                                                                 "function": "virtual ha_rows ha_innobase::records_in_range(uint, key_range*, key_range*)",
                                                                 "table_name": "ITEM",
                                                                 "target_storage_engine": "INNODB"}, "data": [
            {"item_type": "min_key", "properties": {"index_name": "idx_I_PRICE", "length": "3", "operator": ">"},
             "data": [
                 {"item_type": "column_and_bound", "properties": {"column": "I_PRICE", "value": "2.00"}, "data": []}]},
            {"item_type": "max_key", "properties": {"index_name": "idx_I_PRICE", "length": "3", "operator": ">"},
             "data": [
                 {"item_type": "column_and_bound", "properties": {"column": "I_PRICE", "value": "4.00"}, "data": []}]}]}

        req_json['properties']['dbname'] = self.videx_db
        req_json['properties']["videx_options"] = json.dumps({
            "task_id": self.task_id,
            "use_gt": False
        })
        res = self.singleton.ask(
            req_json_item=req_json,
            raise_out=True
        )
        print(res)
        self.assertEqual(res, (200, 'OK', {'value': '49'}))

    def test_multi_gt_lte(self):
        """
        TODO 需要解决
        多值的情况下，第一个都是等值条件，所以当前版本是第一个等值过滤后、第二个执行范围查询.
        然而，如何判断第一列有多少数据？

        如下：第一列的范围是 > 3和 > 3，显然不能简单的做多列的乘法
        此外，目前如果第一列是float，那么过滤后就会只剩下 1 行？

        ################################################################################
        【good new】：然而，innodb 估计出来的也是 1！
        ################################################################################

        EXPLAIN select I_PRICE from ITEM where I_IM_ID = 3 and I_PRICE > 2 and I_PRICE <= 4
        KEY: idx_I_IM_ID_I_PRICE   MIN_KEY: { >  I_IM_ID(3),   I_PRICE(2.00), }, MAX_KEY: { >  I_IM_ID(3),   I_PRICE(4.00), }


        Returns:

        """
        # EXPLAIN select I_PRICE from ITEM where I_IM_ID = 3 and I_PRICE > 2 and I_PRICE <= 4
        # KEY: idx_I_IM_ID_I_PRICE   MIN_KEY: { >  I_IM_ID(3),   I_PRICE(2.00), }, MAX_KEY: { >  I_IM_ID(3),   I_PRICE(4.00), }
        req_json = {"item_type": "videx_request", "properties": {"dbname": "tpcc",
                                                                 "function": "virtual ha_rows ha_innobase::records_in_range(uint, key_range*, key_range*)",
                                                                 "table_name": "ITEM",
                                                                 "target_storage_engine": "INNODB"}, "data": [
            {"item_type": "min_key",
             "properties": {"index_name": "idx_I_IM_ID_I_PRICE", "length": "7", "operator": ">"},
             "data": [{"item_type": "column_and_bound", "properties": {"column": "I_IM_ID", "value": "3"}, "data": []},
                      {"item_type": "column_and_bound", "properties": {"column": "I_PRICE", "value": "2.00"},
                       "data": []}]}, {"item_type": "max_key",
                                       "properties": {"index_name": "idx_I_IM_ID_I_PRICE", "length": "7",
                                                      "operator": ">"}, "data": [
                    {"item_type": "column_and_bound", "properties": {"column": "I_IM_ID", "value": "3"}, "data": []},
                    {"item_type": "column_and_bound", "properties": {"column": "I_PRICE", "value": "4.00"},
                     "data": []}]}]}

        req_json['properties']['dbname'] = self.videx_db
        req_json['properties']["videx_options"] = json.dumps({
            "task_id": self.task_id,
            "use_gt": False
        })
        res = self.singleton.ask(
            req_json_item=req_json,
            raise_out=True
        )
        print(res)
        # I_IM_ID = x0.25, I_PRICE = x(0.8-0.31)，总计 0.25*(0.8-0.31)*100=12.25->12
        # 0.31：decimal，ndv=60，1.cum_freq=0, 3.cum_freq=0.6, 每个值占 0.01，>2的位置处在 0.3+0.01的位置
        self.assertEqual(res, (200, 'OK', {'value': '12'}))


class Test_rec_in_ranges_compare(unittest.TestCase):
    def setUp(self) -> None:
        pass

    def test_single_eq_int(self):
        # EXPLAIN select I_PRICE from ITEM where I_IM_ID = 3
        # KEY: idx_I_IM_ID   MIN_KEY: { =  I_IM_ID(3), }, MAX_KEY: { >  I_IM_ID(3), }
        req_json = {"item_type": "videx_request",
                    "properties": {"dbname": "tpcc",
                                   "function": "virtual ha_rows ha_innobase::records_in_range(uint, key_range*, key_range*)",
                                   "table_name": "ITEM",
                                   "target_storage_engine": "INNODB"}, "data": [
                {"item_type": "min_key",
                 "properties": {"index_name": "idx_I_IM_ID", "length": "4", "operator": "="},
                 "data": [
                     {"item_type": "column_and_bound", "properties": {"column": "I_IM_ID", "value": "3"}, "data": []}]},
                {"item_type": "max_key",
                 "properties": {"index_name": "idx_I_IM_ID", "length": "4", "operator": ">"},
                 "data": [{"item_type": "column_and_bound", "properties": {"column": "I_IM_ID", "value": "3"},
                           "data": []}]}]}

        idx_range = IndexRangeCond.from_dict(*req_json['data'])
        self.assertEqual("idx_I_IM_ID: I_IM_ID = 3", str(idx_range))

    def test_single_lte(self):
        # EXPLAIN select I_PRICE from ITEM where I_IM_ID <= 3
        req_json = {"item_type": "videx_request",
                    "properties": {"dbname": "tpcc",
                                   "function": "virtual ha_rows ha_innobase::records_in_range(uint, key_range*, key_range*)",
                                   "table_name": "ITEM",
                                   "target_storage_engine": "INNODB"},
                    "data": [{"item_type": "min_key", "properties": {}, "data": []}, {"item_type": "max_key",
                                                                                      "properties": {
                                                                                          "index_name": "idx_I_IM_ID",
                                                                                          "length": "4",
                                                                                          "operator": ">"}, "data": [
                            {"item_type": "column_and_bound", "properties": {"column": "I_IM_ID", "value": "3"},
                             "data": []}]}]}

        idx_range = IndexRangeCond.from_dict(*req_json['data'])
        self.assertEqual("idx_I_IM_ID: I_IM_ID <= 3", str(idx_range))

    def test_single_lt(self):
        # EXPLAIN select I_PRICE from ITEM where I_IM_ID < 3
        # KEY: idx_I_IM_ID   MIN_KEY: {<NO_KEY_RANGE>}, MAX_KEY: { <  I_IM_ID(3), }
        req_json = {"item_type": "videx_request", "properties": {"dbname": "tpcc",
                                                                 "function": "virtual ha_rows ha_innobase::records_in_range(uint, key_range *, key_range *)",
                                                                 "table_name": "item",
                                                                 "target_storage_engine": "INNODB"},
                    "data": [{"item_type": "min_key", "properties": {}, "data": []}, {"item_type": "max_key",
                                                                                      "properties": {
                                                                                          "index_name": "idx_s_test",
                                                                                          "length": "4",
                                                                                          "operator": "<"}, "data": [
                            {"item_type": "column_and_bound", "properties": {"column": "I_IM_ID", "value": "3"},
                             "data": []}]}]}

        idx_range = IndexRangeCond.from_dict(*req_json['data'])
        self.assertEqual("idx_s_test: I_IM_ID < 3", str(idx_range))

    def test_single_gt(self):
        # EXPLAIN select I_PRICE from ITEM where I_IM_ID > 3
        # KEY: idx_I_IM_ID   MIN_KEY: { >  I_IM_ID(3), }, MAX_KEY: {<NO_KEY_RANGE>}
        req_json = {"item_type": "videx_request",
                    "properties": {"dbname": "tpcc",
                                   "function": "virtual ha_rows ha_innobase::records_in_range(uint, key_range*, key_range*)",
                                   "table_name": "ITEM",
                                   "target_storage_engine": "INNODB"}, "data": [
                {"item_type": "min_key", "properties": {"index_name": "idx_I_IM_ID", "length": "4", "operator": ">"},
                 "data": [
                     {"item_type": "column_and_bound", "properties": {"column": "I_IM_ID", "value": "3"}, "data": []}]},
                {"item_type": "max_key", "properties": {}, "data": []}]}

        idx_range = IndexRangeCond.from_dict(*req_json['data'])
        self.assertEqual("idx_I_IM_ID: I_IM_ID > 3", str(idx_range))

    def test_single_gte(self):
        # EXPLAIN select I_PRICE from ITEM where I_IM_ID >= 3
        # KEY: idx_I_IM_ID   MIN_KEY: { =  I_IM_ID(3), }, MAX_KEY: {<NO_KEY_RANGE>}
        req_json = {"item_type": "videx_request",
                    "properties": {"dbname": "tpcc",
                                   "function": "virtual ha_rows ha_innobase::records_in_range(uint, key_range*, key_range*)",
                                   "table_name": "ITEM",
                                   "target_storage_engine": "INNODB"}, "data": [
                {"item_type": "min_key", "properties": {"index_name": "idx_I_IM_ID", "length": "4", "operator": "="},
                 "data": [
                     {"item_type": "column_and_bound", "properties": {"column": "I_IM_ID", "value": "3"}, "data": []}]},
                {"item_type": "max_key", "properties": {}, "data": []}]}

        idx_range = IndexRangeCond.from_dict(*req_json['data'])
        self.assertEqual("idx_I_IM_ID: I_IM_ID >= 3", str(idx_range))

    def test_single_col_gte_le(self):
        # EXPLAIN select I_PRICE from ITEM where I_PRICE > 2 and I_PRICE <= 4
        # KEY: idx_I_PRICE   MIN_KEY: { >  I_PRICE(2.00), }, MAX_KEY: { >  I_PRICE(4.00), }
        req_json = {"item_type": "videx_request",
                    "properties": {"dbname": "tpcc",
                                   "function": "virtual ha_rows ha_innobase::records_in_range(uint, key_range*, key_range*)",
                                   "table_name": "ITEM",
                                   "target_storage_engine": "INNODB"}, "data": [
                {"item_type": "min_key", "properties": {"index_name": "idx_I_PRICE", "length": "3", "operator": ">"},
                 "data": [
                     {"item_type": "column_and_bound", "properties": {"column": "I_PRICE", "value": "2.00"},
                      "data": []}]},
                {"item_type": "max_key", "properties": {"index_name": "idx_I_PRICE", "length": "3", "operator": ">"},
                 "data": [
                     {"item_type": "column_and_bound", "properties": {"column": "I_PRICE", "value": "4.00"},
                      "data": []}]}]}

        idx_range = IndexRangeCond.from_dict(*req_json['data'])
        self.assertEqual("idx_I_PRICE: 2.00 < I_PRICE <= 4.00", str(idx_range))

    def test_multi_col_1(self):
        # EXPLAIN select I_PRICE from ITEM where I_IM_ID = 3 and `I_PRICE` < 10 and `I_PRICE` > 3
        # KEY: idx_s_test   MIN_KEY: { >  I_IM_ID(3),   I_PRICE(3.00), }, MAX_KEY: { <  I_IM_ID(3),   I_PRICE(10.00), }
        req_json = {"item_type": "videx_request", "properties": {"dbname": "tpcc",
                                                                 "function": "virtual ha_rows ha_innobase::records_in_range(uint, key_range *, key_range *)",
                                                                 "table_name": "item",
                                                                 "target_storage_engine": "INNODB"}, "data": [
            {"item_type": "min_key", "properties": {"index_name": "idx_s_test", "length": "7", "operator": ">"},
             "data": [{"item_type": "column_and_bound", "properties": {"column": "I_IM_ID", "value": "3"}, "data": []},
                      {"item_type": "column_and_bound", "properties": {"column": "I_PRICE", "value": "3.00"},
                       "data": []}]},
            {"item_type": "max_key", "properties": {"index_name": "idx_s_test", "length": "7", "operator": "<"},
             "data": [{"item_type": "column_and_bound", "properties": {"column": "I_IM_ID", "value": "3"}, "data": []},
                      {"item_type": "column_and_bound", "properties": {"column": "I_PRICE", "value": "10.00"},
                       "data": []}]}]}

        idx_range = IndexRangeCond.from_dict(*req_json['data'])
        print(idx_range)
        self.assertEqual("idx_s_test: I_IM_ID = 3 AND 3.00 < I_PRICE < 10.00", str(idx_range))

    def test_match_str(self):
        # EXPLAIN select I_PRICE from ITEM where I_IM_ID = 3 and `I_PRICE` < 10 and `I_PRICE` > 3
        # KEY: idx_s_test   MIN_KEY: { >  I_IM_ID(3),   I_PRICE(3.00), }, MAX_KEY: { <  I_IM_ID(3),   I_PRICE(10.00), }
        req_json = {"item_type": "videx_request", "properties": {"dbname": "tpcc",
                                                                 "function": "virtual ha_rows ha_innobase::records_in_range(uint, key_range *, key_range *)",
                                                                 "table_name": "item",
                                                                 "target_storage_engine": "INNODB"}, "data": [
            {"item_type": "min_key", "properties": {"index_name": "idx_s_test", "length": "7", "operator": ">"},
             "data": [{"item_type": "column_and_bound", "properties": {"column": "I_IM_ID", "value": "3"}, "data": []},
                      {"item_type": "column_and_bound", "properties": {"column": "I_PRICE", "value": "3.00"},
                       "data": []}]},
            {"item_type": "max_key", "properties": {"index_name": "idx_s_test", "length": "7", "operator": "<"},
             "data": [{"item_type": "column_and_bound", "properties": {"column": "I_IM_ID", "value": "3"}, "data": []},
                      {"item_type": "column_and_bound", "properties": {"column": "I_PRICE", "value": "10.00"},
                       "data": []}]}]}

        idx_range = IndexRangeCond.from_dict(*req_json['data'])
        print(idx_range)
        self.assertEqual("idx_s_test: I_IM_ID = 3 AND 3.00 < I_PRICE < 10.00", str(idx_range))
        gt = GT_Table_Return(idx_gt_pair_dict={
            "idx_s_test": [
                {"range_str": "I_IM_ID = 3 AND 3.00 < I_PRICE < 10.00", "rows": 1282}
            ]
        })
        self.assertEqual(1282, gt.find(idx_range))

    def test_match_2(self):
        min_key, max_key, idx_gt_pair_dict = {'item_type': 'min_key',
                                              'properties': {'index_name': 'idx_L_SHIPDATE', 'length': '3',
                                                             'operator': '='}, 'data': [
                {'item_type': 'column_and_bound', 'properties': {'column': 'L_SHIPDATE', 'value': "'1995-01-01'"},
                 'data': []}]}, {'item_type': 'max_key',
                                 'properties': {'index_name': 'idx_L_SHIPDATE', 'length': '3', 'operator': '>'},
                                 'data': [{'item_type': 'column_and_bound',
                                           'properties': {'column': 'L_SHIPDATE', 'value': "'1996-12-31'"},
                                           'data': []}]}, {
            "idx_L_SHIPDATE": [{"range_str": "'1995-01-01' <= L_SHIPDATE <= '1996-12-31'", "rows": 2896768.0}]}
        idx_range_cond = IndexRangeCond.from_dict(min_key, max_key)
        print(idx_range_cond.ranges_to_str())
        self.assertEqual("'1995-01-01' <= L_SHIPDATE <= '1996-12-31'", idx_range_cond.ranges_to_str())
        gt_return = GT_Table_Return(idx_gt_pair_dict)
        gt = gt_return.find(idx_range_cond)
        print(gt)
        self.assertEqual(2896768, gt)

    def test_match_3(self):
        min_key, max_key, idx_gt_pair_dict = {'item_type': 'min_key',
                                              'properties': {'index_name': 'idx_P_SIZE_P_BRAND', 'length': '4',
                                                             'operator': '='}, 'data': [
                {'item_type': 'column_and_bound', 'properties': {'column': 'P_SIZE', 'value': '5'}, 'data': []}]}, {
            'item_type': 'max_key', 'properties': {'index_name': 'idx_P_SIZE_P_BRAND', 'length': '44', 'operator': '<'},
            'data': [{'item_type': 'column_and_bound', 'properties': {'column': 'P_SIZE', 'value': '5'}, 'data': []},
                     {'item_type': 'column_and_bound', 'properties': {'column': 'P_BRAND', 'value': "'Brand#53'"},
                      'data': []}]}, {
            "idx_P_SIZE_P_BRAND": [{"range_str": "P_SIZE = 5 AND P_BRAND < 'Brand#53'", "rows": 1900.4375},
                                   {"range_str": "P_SIZE = 5 AND 'Brand#53' < P_BRAND", "rows": 1900.4375},
                                   {"range_str": "P_SIZE = 15 AND P_BRAND < 'Brand#53'", "rows": 1900.4375},
                                   {"range_str": "P_SIZE = 15 AND 'Brand#53' < P_BRAND", "rows": 1900.4375},
                                   {"range_str": "P_SIZE = 17 AND P_BRAND < 'Brand#53'", "rows": 1900.4375},
                                   {"range_str": "P_SIZE = 17 AND 'Brand#53' < P_BRAND", "rows": 1900.4375},
                                   {"range_str": "P_SIZE = 18 AND P_BRAND < 'Brand#53'", "rows": 1900.4375},
                                   {"range_str": "P_SIZE = 18 AND 'Brand#53' < P_BRAND", "rows": 1900.4375},
                                   {"range_str": "P_SIZE = 20 AND P_BRAND < 'Brand#53'", "rows": 1900.4375},
                                   {"range_str": "P_SIZE = 20 AND 'Brand#53' < P_BRAND", "rows": 1900.4375},
                                   {"range_str": "P_SIZE = 24 AND P_BRAND < 'Brand#53'", "rows": 1900.4375},
                                   {"range_str": "P_SIZE = 24 AND 'Brand#53' < P_BRAND", "rows": 1900.4375},
                                   {"range_str": "P_SIZE = 36 AND P_BRAND < 'Brand#53'", "rows": 1900.4375},
                                   {"range_str": "P_SIZE = 36 AND 'Brand#53' < P_BRAND", "rows": 1900.4375},
                                   {"range_str": "P_SIZE = 46 AND P_BRAND < 'Brand#53'", "rows": 1900.4375},
                                   {"range_str": "P_SIZE = 46 AND 'Brand#53' < P_BRAND", "rows": 1900.4375}]}
        idx_range_cond = IndexRangeCond.from_dict(min_key, max_key)
        print(idx_range_cond.ranges_to_str())
        self.assertEqual("P_SIZE = 5 AND P_BRAND < 'Brand#53'", idx_range_cond.ranges_to_str())
        gt_return = GT_Table_Return(idx_gt_pair_dict)
        gt = gt_return.find(idx_range_cond)
        print(gt)
        self.assertEqual(1900, gt)

    def test_match_4(self):
        min_key, max_key, idx_gt_pair_dict = \
            {'item_type': 'min_key',
             'properties': {'index_name': 'idx_P_SIZE_P_BRAND', 'length': '44',
                            'operator': '='}, 'data': [
                {'item_type': 'column_and_bound', 'properties': {'column': 'P_SIZE', 'value': '1'}, 'data': []},
                {'item_type': 'column_and_bound', 'properties': {'column': 'P_BRAND', 'value': "'Brand#12'"},
                 'data': []}]}, \
                {'item_type': 'max_key',
                 'properties': {'index_name': 'idx_P_SIZE_P_BRAND', 'length': '44', 'operator': '>'},
                 'data': [
                     {'item_type': 'column_and_bound', 'properties': {'column': 'P_SIZE', 'value': '5'},
                      'data': []}, {'item_type': 'column_and_bound',
                                    'properties': {'column': 'P_BRAND', 'value': "'Brand#32'"},
                                    'data': []}]}, \
                {
                    "idx_P_SIZE_P_BRAND": [{"range_str": "1 <= P_SIZE <= 5", "rows": 34340.0},
                                           {"range_str": "5 < P_SIZE <= 10", "rows": 34340.0},
                                           {"range_str": "10 < P_SIZE <= 15", "rows": 34340.0}],
                    "idx_P_CONTAINER_P_BRAND_P_PARTKEY": [
                        {"range_str": "P_CONTAINER = 'LG BOX' AND P_BRAND = 'Brand#12'", "rows": 203.16666666666666},
                        {"range_str": "P_CONTAINER = 'LG CASE' AND P_BRAND = 'Brand#12'", "rows": 203.16666666666666},
                        {"range_str": "P_CONTAINER = 'LG PACK' AND P_BRAND = 'Brand#12'", "rows": 203.16666666666666},
                        {"range_str": "P_CONTAINER = 'LG PKG' AND P_BRAND = 'Brand#12'", "rows": 203.16666666666666},
                        {"range_str": "P_CONTAINER = 'MED BAG' AND P_BRAND = 'Brand#32'", "rows": 203.16666666666666},
                        {"range_str": "P_CONTAINER = 'MED BOX' AND P_BRAND = 'Brand#32'", "rows": 203.16666666666666},
                        {"range_str": "P_CONTAINER = 'MED PACK' AND P_BRAND = 'Brand#32'", "rows": 203.16666666666666},
                        {"range_str": "P_CONTAINER = 'MED PKG' AND P_BRAND = 'Brand#32'", "rows": 203.16666666666666},
                        {"range_str": "P_CONTAINER = 'SM BOX' AND P_BRAND = 'Brand#24'", "rows": 203.16666666666666},
                        {"range_str": "P_CONTAINER = 'SM CASE' AND P_BRAND = 'Brand#24'", "rows": 203.16666666666666},
                        {"range_str": "P_CONTAINER = 'SM PACK' AND P_BRAND = 'Brand#24'", "rows": 203.16666666666666},
                        {"range_str": "P_CONTAINER = 'SM PKG' AND P_BRAND = 'Brand#24'", "rows": 203.16666666666666}]}

        idx_range_cond = IndexRangeCond.from_dict(min_key, max_key)
        print(idx_range_cond.ranges_to_str())
        self.assertEqual("1 <= P_SIZE <= 5 AND 'Brand#12' <= P_BRAND <= 'Brand#32'", idx_range_cond.ranges_to_str())
        gt_return = GT_Table_Return(idx_gt_pair_dict)
        gt = gt_return.find(idx_range_cond)
        print(gt)
        self.assertEqual(34340, gt)


if __name__ == '__main__':
    pass
