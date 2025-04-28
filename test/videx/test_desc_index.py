# -*- coding: utf-8 -*-
"""
Copyright (c) 2024 Bytedance Ltd. and/or its affiliates
SPDX-License-Identifier: MIT
"""
import unittest
from unittest.mock import patch

from sub_platforms.sql_opt.videx.videx_metadata import construct_videx_task_meta_from_local_files
from sub_platforms.sql_opt.videx.videx_service import VidexSingleton
from sub_platforms.sql_opt.videx.videx_utils import IndexRangeCond, load_json_from_file, \
    join_path


class Test_record_in_ranges_algorithm(unittest.TestCase):

    def setUp(self):
        """
        CREATE TABLE `simple_message` (
          `id` bigint unsigned NOT NULL AUTO_INCREMENT COMMENT 'ID',
          `msg_code` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL DEFAULT '' COMMENT 'message',
          `msg_seq` int NOT NULL DEFAULT '0' COMMENT 'msg_seq',
          `seq_nullable` int DEFAULT NULL COMMENT 'nullable sequence',
          PRIMARY KEY (`id`),
          KEY `idx_code_seq` (`msg_code`,`msg_seq` DESC),
          KEY `idx_desc_seq` (`msg_seq` DESC),
          KEY `idx_nullable_desc` (`seq_nullable` DESC),
          KEY `idx_asc_seq` (`msg_seq`),
          KEY `idx_nullable_asc` (`seq_nullable`)
        ) ENGINE=INNODB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='message table'

        INSERT INTO `simple_message` (`msg_code`, `msg_seq`, `seq_nullable`) VALUES
        ('MSG001', 201, 100),
        ('MSG002', 210, NULL),
        ('MSG003', 225, 150),
        ('MSG004', 240, 500),
        ('MSG005', 255, NULL),
        ('MSG006', 270, 120),
        ('MSG007', 285, 480),
        ('MSG008', 300, NULL),
        ('MSG009', 315, 180),
        ('MSG010', 330, 450),
        ('MSG011', 345, NULL),
        ('MSG012', 360, 130),
        ('MSG013', 375, 470),
        ('MSG014', 390, NULL),
        ('MSG015', 400, 200),
        ('MSG016', 398, 420),
        ('MSG017', 385, NULL),
        ('MSG018', 370, 110),
        ('MSG019', 355, 490),
        ('MSG020', 340, NULL);

        """
        self.singleton = VidexSingleton()
        req_dict = load_json_from_file(join_path(__file__, 'data/videx_metadata_desc_index.json'))

        meta = construct_videx_task_meta_from_local_files(task_id=None,
                                                          videx_db='desc_index',
                                                          stats_file=req_dict.get('stats_dict', {}),
                                                          hist_file=req_dict.get('hist_dict', {}),
                                                          ndv_single_file=req_dict.get('ndv_single_dict', {}),
                                                          ndv_mulcol_file=req_dict.get('ndv_mulcol_dict', {}),
                                                          gt_rec_in_ranges_file=None,
                                                          gt_req_resp_file=None,
                                                          raise_error=True,
                                                          )
        self.singleton.add_task_meta(meta.to_dict())

    def test_1(self):
        input_triplets = [
            ["-- 1. equal + >",
             "EXPLAIN SELECT * FROM simple_message FORCE INDEX (idx_code_seq) WHERE msg_code = 'MSG001' AND msg_seq > 200;",
             "idx_code_seq: msg_code = 'MSG001'; min_side: left, max_side: right AND msg_seq > 200; min_side: right, max_side: None",
             {"item_type": "videx_request", "properties": {"dbname": "desc_index", "function": "virtual ha_rows ha_videx::records_in_range(uint, key_range*, key_range*)", "table_name": "simple_message", "target_storage_engine": "INNODB", "videx_options": "{}"}, "data": [{"item_type": "min_key", "properties": {"index_name": "idx_code_seq", "length": "202", "operator": "="}, "data": [{"item_type": "column_and_bound", "properties": {"column": "msg_code", "value": "'MSG001'"}, "data": []}]}, {"item_type": "max_key", "properties": {"index_name": "idx_code_seq", "length": "206", "operator": "<"}, "data": [{"item_type": "column_and_bound", "properties": {"column": "msg_code", "value": "'MSG001'"}, "data": []}, {"item_type": "column_and_bound", "properties": {"column": "msg_seq", "value": "200"}, "data": []}]}]}
             ],
            ["-- 2. equal + <",
             "EXPLAIN SELECT * FROM simple_message FORCE INDEX (idx_code_seq) WHERE msg_code = 'MSG001' AND msg_seq < 400;",
             "idx_code_seq: msg_code = 'MSG001'; min_side: left, max_side: right AND msg_seq < 400; min_side: None, max_side: left",
             {"item_type": "videx_request", "properties": {"dbname": "desc_index", "function": "virtual ha_rows ha_videx::records_in_range(uint, key_range*, key_range*)", "table_name": "simple_message", "target_storage_engine": "INNODB", "videx_options": "{}"}, "data": [{"item_type": "min_key", "properties": {"index_name": "idx_code_seq", "length": "206", "operator": ">"}, "data": [{"item_type": "column_and_bound", "properties": {"column": "msg_code", "value": "'MSG001'"}, "data": []}, {"item_type": "column_and_bound", "properties": {"column": "msg_seq", "value": "400"}, "data": []}]}, {"item_type": "max_key", "properties": {"index_name": "idx_code_seq", "length": "202", "operator": ">"}, "data": [{"item_type": "column_and_bound", "properties": {"column": "msg_code", "value": "'MSG001'"}, "data": []}]}]}
             ],
            ["-- 3. equal + open range",
             "EXPLAIN SELECT * FROM simple_message FORCE INDEX (idx_code_seq) WHERE msg_code = 'MSG001' AND msg_seq > 200 AND msg_seq < 400;",
             "idx_code_seq: msg_code = 'MSG001'; min_side: left, max_side: right AND 200 < msg_seq < 400; min_side: right, max_side: left",
             {"item_type": "videx_request", "properties": {"dbname": "desc_index", "function": "virtual ha_rows ha_videx::records_in_range(uint, key_range*, key_range*)", "table_name": "simple_message", "target_storage_engine": "INNODB", "videx_options": "{}"}, "data": [{"item_type": "min_key", "properties": {"index_name": "idx_code_seq", "length": "206", "operator": ">"}, "data": [{"item_type": "column_and_bound", "properties": {"column": "msg_code", "value": "'MSG001'"}, "data": []}, {"item_type": "column_and_bound", "properties": {"column": "msg_seq", "value": "400"}, "data": []}]}, {"item_type": "max_key", "properties": {"index_name": "idx_code_seq", "length": "206", "operator": "<"}, "data": [{"item_type": "column_and_bound", "properties": {"column": "msg_code", "value": "'MSG001'"}, "data": []}, {"item_type": "column_and_bound", "properties": {"column": "msg_seq", "value": "200"}, "data": []}]}]}
             ],
            ["-- 4. equal + closed range",
             "EXPLAIN SELECT * FROM simple_message FORCE INDEX (idx_code_seq) WHERE msg_code = 'MSG001' AND msg_seq >= 200 AND msg_seq < 400;",
             "idx_code_seq: msg_code = 'MSG001'; min_side: left, max_side: right AND 200 <= msg_seq < 400; min_side: left, max_side: left",
             {"item_type": "videx_request", "properties": {"dbname": "desc_index", "function": "virtual ha_rows ha_videx::records_in_range(uint, key_range*, key_range*)", "table_name": "simple_message", "target_storage_engine": "INNODB", "videx_options": "{}"}, "data": [{"item_type": "min_key", "properties": {"index_name": "idx_code_seq", "length": "206", "operator": ">"}, "data": [{"item_type": "column_and_bound", "properties": {"column": "msg_code", "value": "'MSG001'"}, "data": []}, {"item_type": "column_and_bound", "properties": {"column": "msg_seq", "value": "400"}, "data": []}]}, {"item_type": "max_key", "properties": {"index_name": "idx_code_seq", "length": "206", "operator": ">"}, "data": [{"item_type": "column_and_bound", "properties": {"column": "msg_code", "value": "'MSG001'"}, "data": []}, {"item_type": "column_and_bound", "properties": {"column": "msg_seq", "value": "200"}, "data": []}]}]}
             ],
            ["-- 5. equal + equal",
             "EXPLAIN SELECT * FROM simple_message FORCE INDEX (idx_code_seq) WHERE msg_code = 'MSG001' AND msg_seq = 200;",
             "idx_code_seq: msg_code = 'MSG001'; min_side: left, max_side: right AND msg_seq = 200; min_side: left, max_side: right",
             {"item_type": "videx_request", "properties": {"dbname": "desc_index", "function": "virtual ha_rows ha_videx::records_in_range(uint, key_range*, key_range*)", "table_name": "simple_message", "target_storage_engine": "INNODB", "videx_options": "{}"}, "data": [{"item_type": "min_key", "properties": {"index_name": "idx_code_seq", "length": "206", "operator": "="}, "data": [{"item_type": "column_and_bound", "properties": {"column": "msg_code", "value": "'MSG001'"}, "data": []}, {"item_type": "column_and_bound", "properties": {"column": "msg_seq", "value": "200"}, "data": []}]}, {"item_type": "max_key", "properties": {"index_name": "idx_code_seq", "length": "206", "operator": ">"}, "data": [{"item_type": "column_and_bound", "properties": {"column": "msg_code", "value": "'MSG001'"}, "data": []}, {"item_type": "column_and_bound", "properties": {"column": "msg_seq", "value": "200"}, "data": []}]}]}
             ],
            ["-- 6. single desc column: >",
             "EXPLAIN SELECT * FROM simple_message FORCE INDEX (idx_desc_seq) WHERE msg_seq > 200;",
             "idx_desc_seq: msg_seq > 200; min_side: right, max_side: None",
             {'item_type': 'videx_request', 'properties': {'dbname': 'desc_index', 'function': 'virtual ha_rows ha_videx::records_in_range(uint, key_range*, key_range*)', 'table_name': 'simple_message', 'target_storage_engine': 'INNODB', 'videx_options': '{}'}, 'data': [{'item_type': 'min_key', 'properties': {}, 'data': []}, {'item_type': 'max_key', 'properties': {'index_name': 'idx_desc_seq', 'length': '4', 'operator': '<'}, 'data': [{'item_type': 'column_and_bound', 'properties': {'column': 'msg_seq', 'value': '200'}, 'data': []}]}]}
             ],
            ["-- 7. single desc column: <",
             "EXPLAIN SELECT * FROM simple_message FORCE INDEX (idx_desc_seq) WHERE msg_seq < 400;",
             "idx_desc_seq: msg_seq < 400; min_side: None, max_side: left",
             {'item_type': 'videx_request', 'properties': {'dbname': 'desc_index', 'function': 'virtual ha_rows ha_videx::records_in_range(uint, key_range*, key_range*)', 'table_name': 'simple_message', 'target_storage_engine': 'INNODB', 'videx_options': '{}'}, 'data': [{'item_type': 'min_key', 'properties': {'index_name': 'idx_desc_seq', 'length': '4', 'operator': '>'}, 'data': [{'item_type': 'column_and_bound', 'properties': {'column': 'msg_seq', 'value': '400'}, 'data': []}]}, {'item_type': 'max_key', 'properties': {}, 'data': []}]}
             ],
            ["-- 8. single desc column: open range",
             "EXPLAIN SELECT * FROM simple_message FORCE INDEX (idx_desc_seq) WHERE msg_seq > 200 AND msg_seq <= 400;",
             "idx_desc_seq: 200 < msg_seq <= 400; min_side: right, max_side: right",
             {"item_type": "videx_request", "properties": {"dbname": "desc_index", "function": "virtual ha_rows ha_videx::records_in_range(uint, key_range*, key_range*)", "table_name": "simple_message", "target_storage_engine": "INNODB", "videx_options": "{}"}, "data": [{"item_type": "min_key", "properties": {"index_name": "idx_desc_seq", "length": "4", "operator": "="}, "data": [{"item_type": "column_and_bound", "properties": {"column": "msg_seq", "value": "400"}, "data": []}]}, {"item_type": "max_key", "properties": {"index_name": "idx_desc_seq", "length": "4", "operator": "<"}, "data": [{"item_type": "column_and_bound", "properties": {"column": "msg_seq", "value": "200"}, "data": []}]}]}
             ],
            ["-- 9. single desc column: closed range",
             "EXPLAIN SELECT * FROM simple_message FORCE INDEX (idx_desc_seq) WHERE msg_seq >= 200 AND msg_seq < 400;",
             "idx_desc_seq: 200 <= msg_seq < 400; min_side: left, max_side: left",
             {"item_type": "videx_request", "properties": {"dbname": "desc_index", "function": "virtual ha_rows ha_videx::records_in_range(uint, key_range*, key_range*)", "table_name": "simple_message", "target_storage_engine": "INNODB", "videx_options": "{}"}, "data": [{"item_type": "min_key", "properties": {"index_name": "idx_desc_seq", "length": "4", "operator": ">"}, "data": [{"item_type": "column_and_bound", "properties": {"column": "msg_seq", "value": "400"}, "data": []}]}, {"item_type": "max_key", "properties": {"index_name": "idx_desc_seq", "length": "4", "operator": ">"}, "data": [{"item_type": "column_and_bound", "properties": {"column": "msg_seq", "value": "200"}, "data": []}]}]}
             ],
            ["-- 10. single desc column: equal",
             "EXPLAIN SELECT * FROM simple_message FORCE INDEX (idx_desc_seq) WHERE msg_seq = 200;",
             "idx_desc_seq: msg_seq = 200; min_side: left, max_side: right",
             {"item_type": "videx_request", "properties": {"dbname": "desc_index", "function": "virtual ha_rows ha_videx::records_in_range(uint, key_range*, key_range*)", "table_name": "simple_message", "target_storage_engine": "INNODB", "videx_options": "{}"}, "data": [{"item_type": "min_key", "properties": {"index_name": "idx_desc_seq", "length": "4", "operator": "="}, "data": [{"item_type": "column_and_bound", "properties": {"column": "msg_seq", "value": "200"}, "data": []}]}, {"item_type": "max_key", "properties": {"index_name": "idx_desc_seq", "length": "4", "operator": ">"}, "data": [{"item_type": "column_and_bound", "properties": {"column": "msg_seq", "value": "200"}, "data": []}]}]}
             ],
            ["-- 11. single desc nullable column: >",
             "EXPLAIN SELECT * FROM simple_message FORCE INDEX (idx_nullable_desc) WHERE seq_nullable > 200;",
             "idx_nullable_desc: seq_nullable > 200; min_side: right, max_side: None",
             {"item_type": "videx_request", "properties": {"dbname": "desc_index", "function": "virtual ha_rows ha_videx::records_in_range(uint, key_range*, key_range*)", "table_name": "simple_message", "target_storage_engine": "INNODB", "videx_options": "{}"}, "data": [{"item_type": "min_key", "properties": {}, "data": []}, {"item_type": "max_key", "properties": {"index_name": "idx_nullable_desc", "length": "5", "operator": "<"}, "data": [{"item_type": "column_and_bound", "properties": {"column": "seq_nullable", "value": "200"}, "data": []}]}]}
             ],
            ["-- 12. single desc nullable column: <",
             "EXPLAIN SELECT * FROM simple_message FORCE INDEX (idx_nullable_desc) WHERE seq_nullable < 400;",
             "idx_nullable_desc: NULL < seq_nullable < 400; min_side: right, max_side: left",
             {"item_type": "videx_request", "properties": {"dbname": "desc_index", "function": "virtual ha_rows ha_videx::records_in_range(uint, key_range*, key_range*)", "table_name": "simple_message", "target_storage_engine": "INNODB", "videx_options": "{}"}, "data": [{"item_type": "min_key", "properties": {"index_name": "idx_nullable_desc", "length": "5", "operator": ">"}, "data": [{"item_type": "column_and_bound", "properties": {"column": "seq_nullable", "value": "400"}, "data": []}]}, {"item_type": "max_key", "properties": {"index_name": "idx_nullable_desc", "length": "5", "operator": "<"}, "data": [{"item_type": "column_and_bound", "properties": {"column": "seq_nullable", "value": "NULL"}, "data": []}]}]}
             ],
            ["-- 13. asc, non-nullable column",
             "EXPLAIN SELECT * FROM simple_message FORCE INDEX (idx_asc_seq) WHERE msg_seq < 400;",
             "idx_asc_seq: msg_seq < 400; min_side: None, max_side: left",
             {"item_type": "videx_request", "properties": {"dbname": "desc_index", "function": "virtual ha_rows ha_videx::records_in_range(uint, key_range*, key_range*)", "table_name": "simple_message", "target_storage_engine": "INNODB", "videx_options": "{}"}, "data": [{"item_type": "min_key", "properties": {}, "data": []}, {"item_type": "max_key", "properties": {"index_name": "idx_asc_seq", "length": "4", "operator": "<"}, "data": [{"item_type": "column_and_bound", "properties": {"column": "msg_seq", "value": "400"}, "data": []}]}]}
             ],
            ["-- 14. asc, non-nullable column",
             "EXPLAIN SELECT * FROM simple_message FORCE INDEX (idx_nullable_asc) WHERE seq_nullable < 400;",
             "idx_nullable_asc: NULL < seq_nullable < 400; min_side: right, max_side: left",
             {"item_type": "videx_request", "properties": {"dbname": "desc_index", "function": "virtual ha_rows ha_videx::records_in_range(uint, key_range*, key_range*)", "table_name": "simple_message", "target_storage_engine": "INNODB", "videx_options": "{}"}, "data": [{"item_type": "min_key", "properties": {"index_name": "idx_nullable_asc", "length": "5", "operator": ">"}, "data": [{"item_type": "column_and_bound", "properties": {"column": "seq_nullable", "value": "NULL"}, "data": []}]}, {"item_type": "max_key", "properties": {"index_name": "idx_nullable_asc", "length": "5", "operator": "<"}, "data": [{"item_type": "column_and_bound", "properties": {"column": "seq_nullable", "value": "400"}, "data": []}]}]}
             ],
        ]
        with patch('sub_platforms.sql_opt.videx.model.videx_model_innodb.VidexModelInnoDB.cardinality') as mock_cardinality:
            for msg, sql, expect_cond, req_json in input_triplets:
                mock_cardinality.return_value = 1
                print("---" * 20)
                print(msg)
                print(sql)
                res = self.singleton.ask(
                    req_json_item=req_json,
                    raise_out=True
                )
                mock_cardinality.assert_called()
                args, kwargs = mock_cardinality.call_args
                idx_cond_seq: IndexRangeCond = args[0]
                actual_cond = idx_cond_seq.to_print_full()
                print(actual_cond)
                self.assertEqual(expect_cond, actual_cond)
        # self.assertEqual(res, (200, 'OK', {'value': '1'}))
