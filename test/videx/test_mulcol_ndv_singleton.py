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
from sub_platforms.sql_opt.videx.videx_utils import load_json_from_file, TestHandler


class Test_mulcol_ndv(unittest.TestCase):
    def setUp(self) -> None:
        self.test_handler = TestHandler()
        self.root_logger = logging.getLogger()  # Get the root logger
        self.root_logger.addHandler(self.test_handler)

    def tearDown(self) -> None:
        self.root_logger.removeHandler(self.test_handler)

    def test_independent_tpch_singleton(self):
        print("test")
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
            gt_rec_in_ranges_file=None,
            gt_req_resp_file=None,
        )

        self.assertTrue(loaded, f"loaded failed")

        def _get_idx_dict(index_name, col_names):
            return {
                "item_type": "key", "properties": {"key_length": "???", "name": index_name},
                "data":
                    [{"item_type": "field", "properties": {"name": c, "store_length": "???"},
                      "data": []} for c in col_names
                     ]
            }

        req_dict = {"item_type": "videx_request",
                    "properties": {"dbname": "videx_tpch", "function": "virtual int ha_videx::info_low(uint, bool)",
                                   "table_name": "???", "target_storage_engine": "INNODB"},
                    "data": [
                    ]
                    }

        gt_mulcol_ndvs = load_json_from_file(os.path.join(test_meta_dir, 'videx_tpch_ndv_mulcol.json'))
        for table_name, table_ndvs in gt_mulcol_ndvs.items():
            print(f"==== test table {table_name}")
            req_dict['properties']['table_name'] = table_name
            req_dict['data'] = []
            for index_name, idx_ndvs in table_ndvs.items():
                first_columns = list(idx_ndvs.keys())
                req_dict['data'].append(_get_idx_dict(index_name, first_columns))

            req_dict['properties']['use_gt'] = False
            resp_actual = videx_meta_singleton.ask(req_json_item=req_dict, raise_out=True)
            req_dict['properties']['use_gt'] = True
            resp_gt = videx_meta_singleton.ask(req_json_item=req_dict, raise_out=True)
            # print(json.dumps(resp_actual, indent=4))
            # print(json.dumps(resp_gt, indent=4))

            for idx_key_actual, ndv_actual in resp_actual[2].items():
                if '#@#' not in idx_key_actual:
                    continue
                ndv_actual = int(float(ndv_actual))
                ndv_gt = int(float(resp_gt[2].get(idx_key_actual)))
                self.assertIsNotNone(ndv_gt, f"not found idx_key_actual={idx_key_actual} in gt")
                if float(ndv_gt) - float(ndv_actual) == 0:
                    # 考虑 0 - 0 的问题
                    err = 0
                else:
                    err = abs(float(ndv_gt) - float(ndv_actual)) / float(ndv_gt)
                if err > 0.15:
                    logging.warning(
                        f"table={table_name}, index={idx_key_actual}, ndv_gt={ndv_gt}, ndv_actual={ndv_actual}, "
                        f"err={err * 100:.4f}%")
                else:
                    logging.info(
                        f"table={table_name}, index={idx_key_actual}, ndv_gt={ndv_gt}, ndv_actual={ndv_actual}, "
                        f"err={err * 100:.4f}%")
                # self.assertLess(err, 0.11, f"table={table_name}, index={idx_key_actual}, err={err} > 10%")

    def test_independent_job_singleton(self):
        print("test")
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
            ndv_mulcol_file=os.path.join(test_meta_dir, 'videx_imdbload_ndv_mulcol.json'),
            gt_rec_in_ranges_file=None,
            gt_req_resp_file=None,
        )

        self.assertTrue(loaded, f"loaded failed")

        req_dict = {"item_type": "videx_request",
                    "properties": {"dbname": "videx_imdbload_nohist",
                                   "function": "virtual int ha_videx::info_low(uint, bool)",
                                   "table_name": "movie_companies",
                                   "target_storage_engine": "INNODB",
                                   "videx_options": "{\"task_id\": \"127_0_0_1_13308@@@demo_imdbload_nohist\", \"use_gt\": false}"},
                    "data": [{"item_type": "key",
                              "properties": {"key_length": "4", "name": "PRIMARY"},
                              "data": [
                                  {"item_type": "field", "properties": {"name": "id", "store_length": "4"},
                                   "data": []}]},
                             {"item_type": "key",
                              "properties": {"key_length": "4", "name": "company_id_movie_companies"}, "data": [
                                 {"item_type": "field", "properties": {"name": "company_id", "store_length": "4"},
                                  "data": []}, {"item_type": "field", "properties": {"name": "id", "store_length": "4"},
                                                "data": []}]}, {"item_type": "key", "properties": {"key_length": "4",
                                                                                                   "name": "company_type_id_movie_companies"},
                                                                "data": [{"item_type": "field",
                                                                          "properties": {"name": "company_type_id",
                                                                                         "store_length": "4"},
                                                                          "data": []}, {"item_type": "field",
                                                                                        "properties": {"name": "id",
                                                                                                       "store_length": "4"},
                                                                                        "data": []}]},
                             {"item_type": "key", "properties": {"key_length": "4", "name": "movie_id_movie_companies"},
                              "data": [{"item_type": "field", "properties": {"name": "movie_id", "store_length": "4"},
                                        "data": []},
                                       {"item_type": "field", "properties": {"name": "id", "store_length": "4"},
                                        "data": []}]}]}

        req_options = json.loads(req_dict['properties']['videx_options'])
        assert req_options.get('task_id') == task_id
        assert req_dict['properties']['dbname'] == videx_db
        res = videx_meta_singleton.ask(req_json_item=req_dict, raise_out=True)
        print(res)
        # self.assertEqual(res, (200, 'OK', {'value': '129399'}))


if __name__ == '__main__':
    pass
