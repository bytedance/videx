# -*- coding: utf-8 -*-
"""
本测试是初始化 singleton，然后测试 ask 函数。除了 flask 网络层，其他都测试到了

@ author: kangrong
@ date: 2023/11/17 
"""
import json
import logging
import os
import unittest

from sub_platforms.sql_opt.videx.videx_service import VidexSingleton
from sub_platforms.sql_opt.videx.videx_utils import IndexRangeCond, TestHandler, \
    load_json_from_file


class Test_ask_rec_in_ranges(unittest.TestCase):
    def setUp(self) -> None:
        self.test_handler = TestHandler()
        self.root_logger = logging.getLogger()  # Get the root logger
        self.root_logger.addHandler(self.test_handler)

    def tearDown(self) -> None:
        self.root_logger.removeHandler(self.test_handler)

    def test_ask_rec_in_ranges_1(self):
        videx_meta_singleton = VidexSingleton()
        task_id = ''
        raw_db = 'tpch'
        videx_db = 'videx_tpch'
        test_meta_dir = os.path.join(os.path.dirname(__file__),
                                     "data/test_tpch_1024")
        loaded = videx_meta_singleton.add_task_meta_from_local_files(
            task_id=task_id,
            raw_db=raw_db,
            videx_db=videx_db,
            stats_file=os.path.join(test_meta_dir, 'videx_tpch_info_stats.json'),
            hist_file=os.path.join(test_meta_dir, 'videx_tpch_histogram.json'),
            ndv_single_file=os.path.join(test_meta_dir, 'videx_tpch_ndv_single.json'),
            ndv_mulcol_file=os.path.join(test_meta_dir, 'videx_tpch_ndv_mulcol.json'),
            gt_rec_in_ranges_file=os.path.join(test_meta_dir, 'gt_rec_in_ranges_wo_idx_innodb.json'),
            gt_req_resp_file=os.path.join(test_meta_dir, 'gt_req_resp.json'),
        )
        self.assertTrue(loaded, f"loaded failed")

        req_dict = {"item_type": "videx_request", "properties": {"dbname": "videx_tpch",
                                                                 "function": "virtual ha_rows ha_videx::records_in_range(uint, key_range *, key_range *)",
                                                                 "table_name": "lineitem",
                                                                 "target_storage_engine": "INNODB"}, "data": [
            {"item_type": "min_key", "properties": {"index_name": "idx_L_SHIPDATE", "length": "3", "operator": "="},
             "data": [{"item_type": "column_and_bound", "properties": {"column": "L_SHIPDATE", "value": "'1995-01-01'"},
                       "data": []}]},
            {"item_type": "max_key", "properties": {"index_name": "idx_L_SHIPDATE", "length": "3", "operator": ">"},
             "data": [{"item_type": "column_and_bound", "properties": {"column": "L_SHIPDATE", "value": "'1996-12-31'"},
                       "data": []}]}]}
        res = videx_meta_singleton.ask(req_json_item=req_dict, raise_out=True)
        print(res)

    def test_ask_rec_in_ranges_2(self):
        videx_meta_singleton = VidexSingleton()
        task_id = ''
        raw_db = 'tpch'
        videx_db = 'videx_tpch'
        test_meta_dir = os.path.join(os.path.dirname(__file__),
                                     "data/test_tpch_1024")
        loaded = videx_meta_singleton.add_task_meta_from_local_files(
            task_id=task_id,
            raw_db=raw_db,
            videx_db=videx_db,
            stats_file=os.path.join(test_meta_dir, 'videx_tpch_info_stats.json'),
            hist_file=os.path.join(test_meta_dir, 'videx_tpch_histogram.json'),
            ndv_single_file=os.path.join(test_meta_dir, 'videx_tpch_ndv_single.json'),
            ndv_mulcol_file=os.path.join(test_meta_dir, 'videx_tpch_ndv_mulcol.json'),
            gt_rec_in_ranges_file=os.path.join(test_meta_dir, 'gt_rec_in_ranges_wo_idx_innodb.json'),
            gt_req_resp_file=os.path.join(test_meta_dir, 'gt_req_resp.json'),
        )
        self.assertTrue(loaded, f"loaded failed")

        req_dict = {"item_type": "videx_request", "properties": {"dbname": "videx_tpch",
                                                                 "function": "virtual ha_rows ha_videx::records_in_range(uint, key_range *, key_range *)",
                                                                 "table_name": "nation",
                                                                 "target_storage_engine": "INNODB"}, "data": [
            {"item_type": "min_key",
             "properties": {"index_name": "idx_N_NAME_N_NATIONKEY", "length": "100", "operator": "="}, "data": [
                {"item_type": "column_and_bound", "properties": {"column": "N_NAME", "value": "'CANADA'"},
                 "data": []}]}, {"item_type": "max_key",
                                 "properties": {"index_name": "idx_N_NAME_N_NATIONKEY", "length": "100",
                                                "operator": ">"}, "data": [
                    {"item_type": "column_and_bound", "properties": {"column": "N_NAME", "value": "'CANADA'"},
                     "data": []}]}]}
        res = videx_meta_singleton.ask(req_json_item=req_dict, raise_out=True)

        assert len(self.test_handler.error_logs) == 0, f"meet error log: {self.test_handler.error_logs}"
        print(res)

    def test_ask_rec_in_ranges_tpch_cases(self):
        # mysql_rows：mysql 估计的结果；gt：真实查出来的结果；expect_rows：期待 videx 估计的结果
        gt_result = {
            # 真值与算法更接近
            "L_SHIPDATE <= '1998-09-18'": {'mysql_rows': 2896768, 'gt_rows': 5943992, 'expect_rows': 5738685},
            "P_SIZE = 24": {'mysql_rows': 3989, 'gt_rows': 3989, 'expect_rows': 3953},
            "R_NAME = 'AMERICA'": {'mysql_rows': 1, 'gt_rows': 1, 'expect_rows': 1},
            "O_ORDERDATE < '1995-03-08'": {'mysql_rows': 740926, 'gt_rows': 722913, 'expect_rows': 713898},
            # 真值与算法更接近
            "L_SHIPDATE > '1995-03-08'": {'mysql_rows': 2896768, 'gt_rows': 3259336, 'expect_rows': 3138392},

            # 真值与算法更接近
            "'1994-02-01' <= O_ORDERDATE < '1994-05-01'": {'mysql_rows': 113652, 'gt_rows': 55462,
                                                           'expect_rows': 54491},
            # 真值与算法更接近
            "'1994-01-01' <= O_ORDERDATE < '1995-01-01'": {'mysql_rows': 455706, 'gt_rows': 227597,
                                                           'expect_rows': 225158},

            "R_NAME = 'EUROPE'": {'mysql_rows': 1, 'gt_rows': 1, 'expect_rows': 1},

            # 真值与算法更接近
            "'1994-01-01' <= L_SHIPDATE < '1995-01-01'": {'mysql_rows': 1740928, 'gt_rows': 909455,
                                                          'expect_rows': 879243},

            # 真值与算法更接近
            "'1995-01-01' <= L_SHIPDATE <= '1996-12-31'": {'mysql_rows': 2896768, 'gt_rows': 1828450,
                                                           'expect_rows': 1768642},

            "N_NAME = 'CANADA'": {'mysql_rows': 1, 'gt_rows': 1, 'expect_rows': 1},
            "N_NAME = 'IRAN'": {'mysql_rows': 1, 'gt_rows': 1, 'expect_rows': 1},

            "P_TYPE = 'LARGE BURNISHED TIN'": {'mysql_rows': 1282, 'gt_rows': 1282, 'expect_rows': 1270},
            # 真值与算法更接近
            "'1995-01-01' <= O_ORDERDATE <= '1996-12-31'": {'mysql_rows': 740926, 'gt_rows': 457263,
                                                            'expect_rows': 452634},
            "L_SHIPMODE = 'MAIL' AND '1993-01-01' <= L_RECEIPTDATE < '1994-01-01'": {'mysql_rows': 252824,
                                                                                     'gt_rows': 129760,
                                                                                     'expect_rows': None}

        }

        videx_meta_singleton = VidexSingleton()
        task_id = ''
        raw_db = 'tpch'
        videx_db = 'videx_tpch'
        test_meta_dir = os.path.join(os.path.dirname(__file__),
                                     "data/test_tpch_1024")
        loaded = videx_meta_singleton.add_task_meta_from_local_files(
            task_id=task_id,
            raw_db=raw_db,
            videx_db=videx_db,
            stats_file=os.path.join(test_meta_dir, 'videx_tpch_info_stats.json'),
            hist_file=os.path.join(test_meta_dir, 'videx_tpch_histogram.json'),
            ndv_single_file=os.path.join(test_meta_dir, 'videx_tpch_ndv_single.json'),
            ndv_mulcol_file=None,
            gt_rec_in_ranges_file=None,
            gt_req_resp_file=None,
        )
        use_gt = False
        # TODO 不传入 ndv_mulcol_file、gt_rec_in_ranges_file、gt_req_resp_file，和传入、但设定 use_gt = False，似乎是一样的？
        #  两种路线需要选一种

        self.assertTrue(loaded, f"loaded failed")

        req_cases = load_json_from_file(os.path.join(test_meta_dir, 'test_cases_tpch_rec_in_range_requests.json'))
        # req_cases = [req_cases[-1]]
        for idx, req_dict in enumerate(req_cases):

            table_name = req_dict['properties']['table_name']
            min_key, max_key = req_dict['data'][:2]
            req_dict['properties']['use_gt'] = use_gt
            idx_range_cond = IndexRangeCond.from_dict(min_key, max_key)
            range_str = idx_range_cond.ranges_to_str()
            if range_str not in gt_result:
                raise ValueError(f"range str ({range_str}) not found in gt_result")
            mysql_rows = gt_result[range_str]['mysql_rows']
            gt_rows = gt_result[range_str]['gt_rows']
            expect_rows = gt_result[range_str]['expect_rows']

            est_rows = videx_meta_singleton.ask(req_json_item=req_dict, raise_out=True)
            est_rows = int(est_rows[2]['value'])
            innodb_err = abs(gt_rows - mysql_rows) / gt_rows
            err = abs(gt_rows - est_rows) / gt_rows
            # print(f"\nidx={idx}, {idx_range_cond.ranges_to_str()}, gt_rows={gt_rows}, est_rows={est_rows}\n")
            print(f"select count(1) from {table_name} where {idx_range_cond.ranges_to_str()}\n",
                  # mysql_rows, gt_rows, est_rows,
                  )
            print("\"%s\": {'mysql_rows':%d, 'gt_rows':%d, 'rows':%d'}, # %s\n" % (
                idx_range_cond.ranges_to_str(), mysql_rows, gt_rows, est_rows,
                f"innodb_err={innodb_err * 100:.2f}% our_err={err * 100:.2f}%"))
            if expect_rows is not None:
                self.assertEqual(expect_rows, est_rows, f"算法估计结果与预设结果：{est_rows} != {expect_rows}")
                self.assertLess(err, 0.05, f"算法和真实查询结果（非 innodb 预估）误差超过5%：{err * 100:.2f}%")

    def test_ask_rec_in_ranges_job_072_20a(self):
        """
        报错：
        cmp result: 072_20a.sql with_gt: http=failed, cmp_res['score']=0.90, cmp_res['msg']='item=3, id=1,
        actual: type=range, expected: type=ALL'.

        原因是 MySQL 会传来 col_int > 'NULL'，报错不支持。修改后，对于 NULL 可以支持。

        Returns:

        """

        videx_meta_singleton = VidexSingleton()
        task_id = '127_0_0_1_13308@@@demo_imdbload_nohist'
        raw_db = 'imdbload_nohist'
        videx_db = 'videx_imdbload_nohist'
        test_meta_dir = os.path.join(os.path.dirname(__file__),
                                     "data/test_imdbload_1024_b10")
        loaded = videx_meta_singleton.add_task_meta_from_local_files(
            task_id=task_id,
            raw_db=raw_db,
            videx_db=videx_db,
            stats_file=os.path.join(test_meta_dir, 'videx_imdbload_info_stats.json'),
            hist_file=os.path.join(test_meta_dir, 'videx_imdbload_histogram_b10.json'),
            ndv_single_file=os.path.join(test_meta_dir, 'videx_imdbload_ndv_single.json'),
            ndv_mulcol_file=None,
            gt_rec_in_ranges_file=None,
            gt_req_resp_file=None,
        )
        use_gt = False

        self.assertTrue(loaded, f"loaded failed")

        req_dict = {"item_type": "videx_request", "properties": {"dbname": "videx_imdbload_nohist",
                                                                 "function": "virtual ha_rows ha_videx::records_in_range(uint, key_range*, key_range*)",
                                                                 "table_name": "complete_cast",
                                                                 "target_storage_engine": "INNODB",
                                                                 "videx_options": "{\"task_id\": \"127_0_0_1_13308@@@demo_imdbload_nohist\", \"use_gt\": false}"},
                    "data": [{"item_type": "min_key",
                              "properties": {"index_name": "movie_id_complete_cast", "length": "5", "operator": ">"},
                              "data": [{"item_type": "column_and_bound",
                                        "properties": {"column": "movie_id", "value": "NULL"}, "data": []}]},
                             {"item_type": "max_key", "properties": {}, "data": []}]}

        req_options = json.loads(req_dict['properties']['videx_options'])
        assert req_options.get('task_id') == task_id
        assert req_dict['properties']['dbname'] == videx_db
        res = videx_meta_singleton.ask(req_json_item=req_dict, raise_out=True)
        print(res)
        self.assertEqual(res, (200, 'OK', {'value': '129399'}))


if __name__ == '__main__':
    pass
