# -*- coding: utf-8 -*-
"""
Copyright (c) 2024 Bytedance Ltd. and/or its affiliates
SPDX-License-Identifier: MIT
"""
import json
import os
import unittest

from sub_platforms.sql_opt.videx.videx_service import VidexSingleton


class Test_info_low(unittest.TestCase):
    def setUp(self):
        # 替换 ITEM 的 histogram，便于测试。测试范围是 I_PRICE、I_IM_ID
        self.singleton = VidexSingleton(pct_cached=1)
        self.task_id = '127_0_0_1_13308@@@demo_tpch'
        self.raw_db = 'tpch'
        self.videx_db = 'videx_tpch'
        self.test_meta_dir = os.path.join(os.path.dirname(__file__),
                                     "data/test_tpch_1024")

    def test_info_with_ndv_mulcol(self):
        """
        explain  SELECT I_IM_ID FROM tpcc.ITEM  force index(idx_I_IM_ID_I_PRICE) where I_IM_ID > 20
        Returns:

        """
        loaded = self.singleton.add_task_meta_from_local_files(
            task_id=self.task_id,
            raw_db=self.raw_db,
            videx_db=self.videx_db,
            stats_file=os.path.join(self.test_meta_dir, 'videx_tpch_info_stats_with_pct_cached.json'),
            hist_file=os.path.join(self.test_meta_dir, 'videx_tpch_histogram.json'),
            ndv_single_file=os.path.join(self.test_meta_dir, 'videx_tpch_ndv_single.json'),
            ndv_mulcol_file=os.path.join(self.test_meta_dir, 'videx_tpch_ndv_mulcol.json'),
            gt_rec_in_ranges_file=None,
            gt_req_resp_file=None,
        )
        self.assertTrue(loaded)

        with open(os.path.join(os.path.dirname(__file__),
                               "data/test_info_item2.json"), "r") as f:
            req_json = json.load(f)
        req_json['properties']["dbname"] = self.videx_db
        req_json['properties']["videx_options"] = json.dumps({
            "task_id": self.task_id,
            "use_gt": True
        })
        res = self.singleton.ask(
            req_json_item=req_json,
            raise_out=True,
            result2str=False
        )
        print(json.dumps(res, indent=4))
        expect_gt = [
            200,
            "OK",
            {
                'stat_n_rows': 5799239,
                "stat_clustered_index_size": 57152,
                'stat_sum_of_other_index_sizes': 69962,
                "data_file_length": 936378368,
                'index_file_length': 1146257408,
                'innodb_buffer_pool_size': 4294967296,
                "data_free_length": 2097152,
                # note, you can specify pct_cached to use gt, 0, or 1 as default
                'pct_cached #@# LINEITEM_FK1': 1,
                'pct_cached #@# LINEITEM_FK2': 1,
                'pct_cached #@# LINEITEM_UK1': 1,
                'pct_cached #@# PRIMARY': 1,
                # 'pct_cached #@# LINEITEM_FK1': 0.0,
                # 'pct_cached #@# LINEITEM_FK2': 1.0,
                # 'pct_cached #@# LINEITEM_UK1': 1.0,
                # 'pct_cached #@# PRIMARY': 0.8475,
                'rec_per_key #@# LINEITEM_FK1 #@# L_ID': 1.0,
                'rec_per_key #@# LINEITEM_FK1 #@# L_ORDERKEY': 3.880374438359189,
                'rec_per_key #@# LINEITEM_FK2 #@# L_ID': 1.0,
                'rec_per_key #@# LINEITEM_FK2 #@# L_PARTKEY': 30.66093020550806,
                'rec_per_key #@# LINEITEM_FK2 #@# L_SUPPKEY': 7.353160308518232,
                'rec_per_key #@# LINEITEM_UK1 #@# L_LINENUMBER': 1.0,
                'rec_per_key #@# LINEITEM_UK1 #@# L_ORDERKEY': 3.9050747044547935,
                'rec_per_key #@# PRIMARY #@# L_ID': 1.000984372928726,
            }
        ]
        self.assertEqual(tuple(expect_gt), res)

    def test_info_without_ndv_mulcol(self):
        """
        explain  SELECT I_IM_ID FROM tpcc.ITEM  force index(idx_I_IM_ID_I_PRICE) where I_IM_ID > 20
        Returns:

        """
        loaded = self.singleton.add_task_meta_from_local_files(
            task_id=self.task_id,
            raw_db=self.raw_db,
            videx_db=self.videx_db,
            stats_file=os.path.join(self.test_meta_dir, 'videx_tpch_info_stats_with_pct_cached.json'),
            hist_file=os.path.join(self.test_meta_dir, 'videx_tpch_histogram.json'),
            ndv_single_file=os.path.join(self.test_meta_dir, 'videx_tpch_ndv_single.json'),
            ndv_mulcol_file=None,  # without ndv,则此处留 None
            gt_rec_in_ranges_file=None,
            gt_req_resp_file=None,
        )
        self.assertTrue(loaded)

        with open(os.path.join(os.path.dirname(__file__),
                               "data/test_info_item2.json"), "r") as f:
            req_json = json.load(f)
        req_json['properties']["dbname"] = self.videx_db
        req_json['properties']["videx_options"] = json.dumps({
            "task_id": self.task_id,
            # "use_gt": False
        })
        res = self.singleton.ask(
            req_json_item=req_json,
            raise_out=True,
            result2str=False
        )
        print(json.dumps(res, indent=4))
        expect_nogt = [
            200,
            'OK',
            {'data_file_length': 936378368,
             'data_free_length': 2097152,
             'index_file_length': 1146257408,
             'innodb_buffer_pool_size': 4294967296,
             # 注意，pct_cached 是否使用 gt、默认值取 0 或者 1 ，是根据策略而定的。当策略更新后，直接把 expect 改掉即可
             # 修改后
             # 'pct_cached #@# LINEITEM_FK1': 0,
             # 'pct_cached #@# LINEITEM_FK2': 0,
             # 'pct_cached #@# LINEITEM_UK1': 0,
             # 'pct_cached #@# PRIMARY': 0,
             # 修改前
             'pct_cached #@# LINEITEM_FK1': 1,
             'pct_cached #@# LINEITEM_FK2': 1,
             'pct_cached #@# LINEITEM_UK1': 1,
             'pct_cached #@# PRIMARY': 1,
             'rec_per_key #@# LINEITEM_FK1 #@# L_ID': 1.0,
             'rec_per_key #@# LINEITEM_FK1 #@# L_ORDERKEY': 3.8661593333333335,
             'rec_per_key #@# LINEITEM_FK2 #@# L_ID': 1.0,
             'rec_per_key #@# LINEITEM_FK2 #@# L_PARTKEY': 28.996195,
             'rec_per_key #@# LINEITEM_FK2 #@# L_SUPPKEY': 1.0,
             'rec_per_key #@# LINEITEM_UK1 #@# L_LINENUMBER': 1.0,
             'rec_per_key #@# LINEITEM_UK1 #@# L_ORDERKEY': 3.8661593333333335,
             'rec_per_key #@# PRIMARY #@# L_ID': 1.0,
             'stat_clustered_index_size': 57152,
             'stat_n_rows': 5799239,
             'stat_sum_of_other_index_sizes': 69962},
        ]
        self.assertEqual(tuple(expect_nogt), res)


if __name__ == '__main__':
    pass
