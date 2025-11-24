"""
Copyright (c) 2024 Bytedance Ltd. and/or its affiliates
SPDX-License-Identifier: MIT
"""

import enum
import gzip
import json
import logging
import re
import threading
import time
import traceback
from dataclasses import dataclass, field
from typing import List, Tuple, Union, Callable, Type, Dict, Optional

import requests
from cachetools import TTLCache
from flask import Flask, request, jsonify
from flask_restx import Api, Resource, fields, Namespace
from requests import Response

from sub_platforms.sql_opt.env.rds_env import Env
from sub_platforms.sql_opt.videx import videx_logging
from sub_platforms.sql_opt.videx.videx_metadata import VidexTableStats, VidexDBTaskStats, EXTRA_INFO_KEY_pct_cached, \
    EXTRA_INFO_KEY_mulcol, EXTRA_INFO_KEY_gt_rec_in_ranges, construct_videx_task_meta_from_local_files
from sub_platforms.sql_opt.videx.model.videx_strategy import VidexModelBase
from sub_platforms.sql_opt.videx.model.videx_model_innodb import VidexModelInnoDB
from sub_platforms.sql_opt.videx.videx_utils import GT_Table_Return, get_local_ip, get_func_with_parent

app = Flask(__name__)
ENV_KEY_POST_VIDEX_META = 'POST_VIDEX_META'

# Create API object
api = Api(
    app,
    version='1.0',
    title='VIDEX API',
    description='This API doc integrates Swagger support into the VIDEX server using the Flask-RESTX, providing automated API description and interactive testing.',
    doc='/docs',
    ui=True,
    validate=True
)

# Define a single namespace to maintain original path compatibility
ns = api.namespace('', description='VIDEX API List')

# Standard response model
response_model = api.model('Response', {
    'code': fields.Integer(required=True, description='Status Code'),
    'message': fields.String(required=True, description='Response Message'),
    'data': fields.Raw(description='Response Data')
})

# define a nullable string field
class NullableString(fields.Raw):
    __schema_type__ = ['string', 'null']
    __nullable__ = True

    def format(self, value):
        if value is None or isinstance(value, str):
            return value
        raise ValueError('task_id must be string or null')

task_meta_model = api.model('TaskMeta', {
    'task_id': NullableString(required=True, description='Task ID'),
    'meta_dict': fields.Raw(required=True, description='Meta Dictionary'),
    'stats_dict': fields.Raw(required=True, description='Stats Dictionary'),
    'db_config': fields.Raw(required=True, description='DB Config')
})

ask_videx_model = api.model('AskVidex', {
    'item_type': fields.String(required=True, description='item type'),
    'properties': fields.Nested(api.model('VidexProperties', {
        'dbname': fields.String(required=True, description='database name'),
        'function': fields.String(required=True, description='function name'),
        'table_name': fields.String(required=True, description='table name'),
        'target_storage_engine': fields.String(required=True, description='target storage engine'),
        'videx_options': fields.String(required=False, description='Videx options JSON string')
    }), required=True, description='Videx properties'),
    'data': fields.List(fields.Raw, required=True, description='List of data items')
})

clear_cache_model = api.model('ClearCache', {
    'key_list': fields.List(fields.String, required=False, description='List of keys to clear')
})

update_gt_stats_model = api.model('UpdateGTStats', {
    'task_id': NullableString(required=True, description='Task ID'),
    'gt_stats_file': fields.Raw(required=True, description='GT stats file'),
    'gt_ndv_mulcol_file': fields.Raw(required=True, description='GT ndv mulcol file'),
    'gt_rec_in_ranges': fields.Raw(required=False, description='GT rec in ranges'),
    'gt_req_resp': fields.Raw(required=True, description='GT req resp')
})

class VidexFunc(enum.Enum):
    scan_time = "scan_time"
    get_memory_buffer_size = "get_memory_buffer_size"
    records_in_range = "records_in_range"
    info_low = "info_low"
    videx_get_relation_stats = "videx_get_relation_stats"
    not_supported = "not_supported"


def str2VidexFunc(s: str) -> VidexFunc:
    for func in VidexFunc:
        if func.value.lower() in s.lower():
            return func
    return VidexFunc.not_supported


@dataclass
class VidexTaskCache:
    """
    Task cache, including metadata from one or multiple databases, and the initialized videx algorithm model
    Both of them will be cleared according to TTL cached.
    """

    # contains multi dbs: db -> table -> VidexTableStats
    db_tasks_stats: Optional[VidexDBTaskStats] = None

    """
    db -> table -> VidexTableStats
    when calling, init VidexModel and set into it:
    """
    model_cache_dict: Optional[Dict[str, Dict[str, Optional[VidexModelBase]]]] = field(default_factory=dict)

    def __post_init__(self):
        self.model_cache_dict = {k.lower(): {k1.lower(): v1 for k1, v1 in v.items()} for k, v in
                                 self.model_cache_dict.items()}

    def add_db_tasks_stats(self, stats: VidexDBTaskStats):
        if self.db_tasks_stats is None:
            self.db_tasks_stats = stats
        else:
            self.db_tasks_stats.merge_with(stats, inplace=True)
            # discard model cache if db and table exists
            for db_name, table_list in self.db_tasks_stats.get_meta_info_keys().items():
                if db_name not in self.model_cache_dict:
                    self.model_cache_dict[db_name] = {}
                for table_name in table_list:
                    if table_name in self.model_cache_dict[db_name]:
                        logging.info(f"discard exist model cache: {db_name}.{table_name}")
                        self.model_cache_dict[db_name][table_name] = None

    def get_table_model_cache(self, db_name: str, table_name: str) -> Optional[VidexModelBase]:
        db_name = db_name.lower()
        table_name = table_name.lower()
        return self.model_cache_dict.get(db_name, {}).get(table_name)

    def add_table_model_cache(self, db_name: str, table_name: str, table_model: VidexModelBase):
        db_name = db_name.lower()
        table_name = table_name.lower()
        if db_name not in self.model_cache_dict:
            self.model_cache_dict[db_name] = {}
        self.model_cache_dict[db_name][table_name] = table_model


class VidexSingleton:
    def __init__(self,
                 # raw_meta_data: Union[str, dict], histogram_data: Union[str, dict],
                 # ideal_ndv_file: str = None,
                 # single_ndv_file: str = None,
                 load_meta_by_task_id_func: Callable[[str], VidexDBTaskStats] = None,
                 VidexModelClass: Type[VidexModelBase] = VidexModelInnoDB,
                 logging_package=videx_logging,
                 **model_kwargs,
                 ):
        self.lock = threading.RLock()
        # Double-layered defaultdict
        # Caches Videx information, holds a maximum of 100,000 records, and retains them for 300 seconds.
        self.cache: TTLCache[str, VidexTaskCache] = TTLCache(maxsize=1000, ttl=300)
        # non task cache is regarded as long-term cache, item is evicted only if exceeding cache size.
        self.non_task_cache: VidexTaskCache = VidexTaskCache(db_tasks_stats=None)
        # load meta by task_id
        self.load_meta_by_task_id_func = load_meta_by_task_id_func
        self.VidexModelClass = VidexModelClass
        self.request_count = 0
        self.model_kwargs = model_kwargs
        self.logging_package = logging_package
        self.logging_package.initial_config()

    def extract_task_id(self, req_json_item) -> Optional[str]:
        properties = req_json_item.get('properties', {})
        videx_options = json.loads(properties.get('videx_options', "{}"))
        task_id = videx_options.get('task_id')
        if task_id is None or task_id == 'None' or task_id == '':
            return None
        else:
            return task_id

    def ask(self, req_json_item: dict, result2str: bool = True, raise_out: bool = False) \
            -> Tuple[int, str, dict]:
        if req_json_item.get('properties') is None or not isinstance(req_json_item['properties'], dict):
            return 502, f"miss 'properties' or properties is not dict", {}
        properties = req_json_item['properties']

        if not {'dbname', 'table_name', 'function'}.issubset(properties.keys()):
            return 502, f"miss input: target_engine: " \
                        f"required dbname, table_name, function, but received properites: {properties}", {}
        target_engine = properties.get('target_engine', "innodb")
        videx_db = properties['dbname'].lower()
        table_name = properties['table_name'].lower()
        func_str = properties['function'].lower()

        # N.B. videx_options passing chain:
        # OPTIMIZE_TASK sets the user variable VIDEX_OPTIONS to the VIDEX_MYSQL instance.
        # VIDEX_MYSQL receives VIDEX_OPTIONS, renames it to videx_options, and forwards it to VIDEX_SERVER.
        # VIDEX_SERVER receives videx_options and processes it.
        # videx_options = json.loads(properties.get('videx_options', "{}"))
        task_id = self.extract_task_id(req_json_item)
        # use_gt = videx_options.get('use_gt', True)

        if task_id is None:
            task_cache = self.non_task_cache
            db_task_stats = task_cache.db_tasks_stats
        elif task_id in self.cache:
            task_cache = self.cache.get(task_id)
            db_task_stats = task_cache.db_tasks_stats
        elif self.load_meta_by_task_id_func is None:
            logging.error(f"=== to find {task_id}, not in cache and load_meta_by_task_id_func is None. {req_json_item=}")
            return 502, f"db task key not in cache and load_func is None: given task_key={task_id}, " \
                        f"videx_db={videx_db}, we have: {list(self.cache.keys())}", {}
        else:
            func_name = get_func_with_parent(self.load_meta_by_task_id_func)
            st = time.perf_counter()
            db_task_stats: VidexDBTaskStats = self.load_meta_by_task_id_func(task_id)
            end = time.perf_counter()
            if db_task_stats is None:
                logging.error(f"=== loading task_meta failed by using func {func_name}. {task_id=} {req_json_item=}")
                return 502, f"load task_meta using func={func_name}, ", {}

            task_cache = VidexTaskCache(db_task_stats)
            before_keys = list(self.cache.keys())
            self.cache[task_id] = task_cache
            now_keys = list(self.cache.keys())

            db_tables = {db: {tb for tb in v} for db, v in db_task_stats.stats_dict.items()}
            logging.info(f"=== load task_meta using func={func_name}. use {end - st:.2f}s. "
                         f"key={db_task_stats.key} db:tables={db_tables} {before_keys=} {now_keys=}")

        if db_task_stats is None:
            logging.info(f"=== to find {task_id}, not find. {req_json_item=}")
            return 502, f"db task key not found: given task_key={task_id}, " \
                        f"videx_db={videx_db}, we have: {list(self.cache.keys())}", {}

        success_code, success_msg = 200, "OK"

        # If an expect request already exists, return immediately.
        # The new version has removed the use of `use_gt`. Control the usage of gt by passing {req_json_item: expect_resp}.
        expect_resp = db_task_stats.get_expect_response(req_json_item, result2str)
        if expect_resp is not None:
            return success_code, success_msg, expect_resp

        if db_task_stats.get_table_meta(videx_db, table_name) is None:
            return 404, f"Not Found table_name: {videx_db}.{table_name}", {}
        func = str2VidexFunc(func_str)
        if func == VidexFunc.not_supported:
            return 400, f"Not Supported function: {func_str}", {}

        # TODO  For ease of debugging, directly construct the InnoDB model.
        table_model = self.get_videx_table_stats(task_cache, videx_db, table_name)
        resp = {}
        single_resp = lambda v: {"value": v}
        # #########################################################
        # ##################### key part ##########################
        # #########################################################
        # TODO Consider code optimization and encapsulation later.
        try:
            if func == VidexFunc.scan_time:
                resp = single_resp(table_model.scan_time(req_json_item))
            elif func == VidexFunc.get_memory_buffer_size:
                resp = single_resp(table_model.get_memory_buffer_size(req_json_item))
            elif func == VidexFunc.records_in_range:
                resp = single_resp(table_model.records_in_range(req_json_item))
            elif func == VidexFunc.info_low:
                resp = table_model.info_low(req_json_item)
            else:
                raise NotImplementedError(f"MEEEET func unsupported: {func}")
        except Exception as e:
            if raise_out:
                raise
            logging.error(f"meet error in {target_engine}, {videx_db}, {table_name}, {func_str}: {e}, "
                          f"{traceback.format_exc()}")
            return 500, str(e), {}
        if result2str:
            final_resp = {k: str(v) for k, v in resp.items()}
        else:
            final_resp = resp
        return success_code, success_msg, final_resp

    def get_videx_table_stats(self, task_cache: VidexTaskCache, db_name: str, table_name: str) -> VidexModelBase:
        db_task_stats = task_cache.db_tasks_stats

        if (res := task_cache.get_table_model_cache(db_name, table_name)) is not None:
            return res

        if (table_stats_info := db_task_stats.get_table_stats_info(db_name, table_name)) is None:
            raise ValueError(f"given db_stats_info have not {db_name=} {table_name=}, only: {db_task_stats.get_stats_info_keys()}")

        if (table_meta := db_task_stats.get_table_meta(db_name, table_name)) is None:
            raise ValueError(f"given db_meta_info have not {db_name=} {table_name=}, only: {db_task_stats.get_meta_info_keys()}")

        gt_rec_in_ranges = table_stats_info.extra_info.get(EXTRA_INFO_KEY_gt_rec_in_ranges, [])
        gt_rr_dict = GT_Table_Return.parse_raw_gt_rec_in_range_list(gt_rec_in_ranges)

        table_stats = VidexTableStats.from_json(
            dbname=db_name,
            table_name=table_name,
            raw_meta_dict=table_meta,
            hist_columns=table_stats_info.histogram_dict,
            sample_file_info=db_task_stats.sample_file_info,
            db_config=db_task_stats.db_config,
            ideal_ndvs=table_stats_info.extra_info.get(EXTRA_INFO_KEY_mulcol),
            single_ndvs=table_stats_info.ndv_dict,
            pct_cached=table_stats_info.extra_info.get(EXTRA_INFO_KEY_pct_cached),
            #  Note: Do not replace `gt_rr_dict[table_name]` with `x.get(y)`, as `gt_rr_dict` is a `defaultdict(GT_Table_Return)`.
            # It returns a default `GT_Table_Return` only when calling `gt_rr_dict[table_name]`.
            # `gt_rr_dict.get(table_name)` would return `None` if the key does not exist.
            gt_rec_in_ranges=gt_rr_dict[table_name],
            sample_data=table_stats_info.sample_data
        )
        table_model = self.VidexModelClass(table_stats, **self.model_kwargs)
        task_cache.add_table_model_cache(db_name, table_name, table_model)
        return table_model

    def add_task_meta_from_local_files(self, task_id, raw_db, videx_db,
                                       stats_file: Union[str, dict],
                                       hist_file: Union[str, dict],
                                       ndv_single_file: Union[str, dict],
                                       ndv_mulcol_file: Union[str, dict] = None,
                                       gt_rec_in_ranges_file: Union[str, dict] = None,
                                       gt_req_resp_file: Union[str, dict] = None,
                                       raise_error: bool = False,
                                       server_ip_port: str = None,
                                       **kwargs
                                       ) -> Union[bool, Response]:
        """
        Add task metadata from a local file.
        Args:
            task_id:
            raw_db:
            videx_db:
            stats_file:
            hist_file:
            ndv_single_file:
            # ndv_mulcol_file: In real scenarios, if an index has been created, there may be mulcol_ndv,
                but it might not be provided at all, in which case rely on single column ndv estimation.


            gt_rec_in_ranges_file:
            gt_req_resp_file:
            raise_error:

        Returns:
            bool: true if added successfully

        """

        req_obj = construct_videx_task_meta_from_local_files(task_id=task_id,
                                                             videx_db=videx_db,
                                                             stats_file=stats_file,
                                                             hist_file=hist_file,
                                                             ndv_single_file=ndv_single_file,
                                                             ndv_mulcol_file=ndv_mulcol_file,
                                                             gt_rec_in_ranges_file=gt_rec_in_ranges_file,
                                                             gt_req_resp_file=gt_req_resp_file,
                                                             raise_error=raise_error,
                                                             )
        if not server_ip_port:
            self.add_task_meta(req_obj.to_dict())
            return True
        else:
            return post_add_videx_meta(req_obj, server_ip_port, use_gzip=True)

    def add_task_meta(self, req_dict: dict):
        """
        为：
        req_dict = {
            "task_id": task_id,
            "stats_dict": {},
            "meta_dict": {},
        }

        Returns:

        """
        videx_request: VidexDBTaskStats = VidexDBTaskStats.from_dict(req_dict)

        db_tables = {db: {tb for tb in v} for db, v in videx_request.stats_dict.items()}

        if videx_request.key_is_none():
            before_meta_keys = None
            if self.non_task_cache.db_tasks_stats is not None:
                before_meta_keys = self.non_task_cache.db_tasks_stats.get_meta_info_keys()

            self.non_task_cache.add_db_tasks_stats(videx_request)

            after_meta_keys = self.non_task_cache.db_tasks_stats.get_meta_info_keys()
            logging.info(f"=== load NON-TASK-ID task_meta. "
                         f"New db:tables={db_tables} {before_meta_keys=} {after_meta_keys=}")
            return

        before_keys = list(self.cache.keys())
        self.cache[videx_request.key] = VidexTaskCache(videx_request)
        now_keys = list(self.cache.keys())
        # 只有这里可能要加锁
        logging.info(f"=== load task_meta for key={videx_request.key} db:tables={db_tables} {before_keys=} {now_keys=}")


    def clear_cache(self, req_dict):
        key_list = req_dict.get('key_list', [])
        before_keys = list(self.cache.keys())
        if key_list is None or len(key_list) == 0:
            self.cache.clear()
            self.non_task_cache = VidexTaskCache(db_tasks_stats=None)
            logging.info("all task caches cleared")
        else:
            for key in key_list:
                if key in self.cache:
                    self.cache.pop(key)

        logging.info(f"cache is cleared: to clear: {key_list} "
                     f"before={list(before_keys)} "
                     f"now={list(self.cache.keys())} ")


# request_count = 0
# resp_expect_dict = {}


@app.before_request
def before_request():
    if 'Content-Encoding' in request.headers and request.headers['Content-Encoding'] == 'gzip':
        decompressed_data = gzip.decompress(request.get_data(cache=False))

        # update the request header and data
        request._cached_data = decompressed_data
        # del request.headers['Content-Encoding']


@ns.route('/create_task_meta')
class CreateTaskMeta(Resource):
    @ns.doc('Create Task Meta')
    @ns.expect(task_meta_model)
    @ns.response(200, 'Success', response_model)
    @ns.response(400, 'Validation Error')
    def post(self):
        req_json_item = api.payload
        global videx_meta_singleton
        videx_meta_singleton.add_task_meta(req_json_item)
    
        code, message, response_data = 200, "OK", {}
        return jsonify(code=code, message=message, data=response_data)


@ns.route('/clear_cache')
class ClearCache(Resource):
    @ns.doc('Clear Cache')
    @ns.expect(clear_cache_model)
    @ns.response(200, 'Success', response_model)
    def post(self):
        global videx_meta_singleton
        videx_meta_singleton.clear_cache({})

        code, message, response_data = 200, "OK", {}
        return jsonify(code=code, message=message, data=response_data)



@ns.route('/update_gt_stats')
class UpdateGTStats(Resource):
    @ns.doc('Update GT Stats')
    @ns.expect(update_gt_stats_model)
    @ns.response(200, 'Success', response_model)
    def post(self):
        # 提供 gt 结果，用于测试 videx-py 的其他环节是否正确。这些 gt 可能由于算法无法完美贴合 innodb（多列 ndv、多列 rec_in_ranges），
        # 也可能是由于新建索引后一些统计量变化。
        #
        # 传入格式为：
        #     req_dict = {
        #         "task_id": task_id,
        #         "gt_stats_file": load_json_from_file(expect_meta_files[0]),
        #         "gt_ndv_mulcol_file": load_json_from_file(expect_meta_files[3]),
        #         "gt_rec_in_ranges": gt_rec_in_ranges,  # 可能为空
        #         "gt_req_resp": gt_req_resp,
        #     }
        # 注意，收集最耗时的 "hist_file", "ndv_single_file" 反倒不会因为建删索引而变化，因此 update_gt_stats 不需要传入这些
        #
        # Returns:
        #     创建成功与否
        raise NotImplementedError


@ns.route('/set_task_variables')
class SetTaskVariables(Resource):
    @ns.doc('set task variables')
    @ns.response(200, 'Success', response_model)
    def post(self):
        # 主要是指定某个 task 是否启用 gt 数据
        raise NotImplementedError


@ns.route('/ask_videx')
class AskVidex(Resource):
    @ns.doc('Ask VIDEX')
    @ns.expect(ask_videx_model)
    @ns.response(200, 'Success', response_model)
    @ns.response(400, 'Validation Error')
    @ns.response(404, 'Table Not Found')
    @ns.response(502, 'Bad Gateway')
    def post(self):
        req_json_item = api.payload
        global videx_meta_singleton
        # global request_count
        # global resp_expect_dict
        
        # set task id
        req_idx = videx_meta_singleton.request_count
        task_id = videx_meta_singleton.extract_task_id(req_json_item)
        videx_meta_singleton.logging_package.set_thread_trace_id(f"<<{task_id}#{req_idx}>>")
        videx_meta_singleton.request_count += 1
        logging.info(f"[{req_idx}] ==== receive data, {json.dumps(req_json_item)}")

        st = time.perf_counter()
        code, message, response_data = videx_meta_singleton.ask(req_json_item)
        elapsed_time = time.perf_counter() - st
        
        if code == 200:
            logging.info(f"[{req_idx}] == [{code=}] use {elapsed_time:.2f}s response data: {json.dumps(response_data)}")
        else:
            logging.error(f"[{req_idx}] == [{code=}] use {elapsed_time:.2f}s {message=} "
                          f"response data: ={json.dumps(response_data)}")
        return jsonify(code=code, message=message, data=response_data)


@ns.route('/videx/visualization/get_stats')
class GetStats(Resource):
    @ns.doc('get stats')
    @ns.response(200, 'Success', response_model)
    def get(self):
        # 返回 videx_meta_singleton 当前的缓存大小。
        non_task_cache: VidexTaskCache = videx_meta_singleton.non_task_cache
        data_dict = {}
        if non_task_cache is not None and non_task_cache.db_tasks_stats is not None:
            data_dict = json.loads(non_task_cache.db_tasks_stats.to_json())
        code, message, response_data = 200, "OK", {'stats': data_dict}
        return jsonify(code=code, message=message, data=response_data)

@ns.route('/videx/visualization/status')
class Status(Resource):
    @ns.doc('status')
    @ns.response(200, 'Success', response_model)
    def get(self):
        # 返回 videx_meta_singleton 当前的缓存大小。
        code, message, response_data = 200, "OK", {'cache': dict(videx_meta_singleton.cache)}
        return jsonify(code=code, message=message, data=response_data)


def post_add_videx_meta(req: VidexDBTaskStats, videx_server_ip_port: str, use_gzip: bool):
    # 1. 将 src_meta 导入videx-py
    json_data = req.to_json().encode('utf-8')
    if use_gzip:
        # 转换 JSON 数据为字符串，并用 UTF-8 编码为 bytes
        json_data = gzip.compress(json_data)  # 使用 gzip 进行压缩
        headers = {'Content-Encoding': 'gzip', 'Content-Type': 'application/json'}
    else:
        headers = {'Content-Type': 'application/json'}
    # send request
    logging.info(f"post videx metadata to {videx_server_ip_port}")
    return requests.post(f'http://{videx_server_ip_port}/create_task_meta', data=json_data, headers=headers)


def create_videx_env_multi_db(videx_env: Env,
                              meta_dict: dict,
                              new_engine: str = 'VIDEX',
                              ):
    """
    Specify a target database (`target_db`), retrieve metadata, and create it on the `videx_db` within the `videx_env`.

     Args:
        meta_dict: Dictionary containing metadata.
        videx_env: Integrated environment for Videx MySQL and Parse MySQL.
        // meta_dir: Metadata already fetched. Tuple of four elements: info_stats, hist, ndv_single, ndv_multi
        // gt_rec_in_ranges: Used to return gt results for `rec_in_ranges`.
            Each element contains range conditions and gt rows.
            Data is collected from executing explain on innodb, tracing range queries and (gt) rows information.
        // gt_req_resp: Used to return gt for any request.
            Element is a tuple of three: request json, response json, turn_on (whether to enable).
            If a request matches an enabled element, it returns directly.
        new_engine: Name of the engine to be created.
    Returns:

    """
    # Create a test database named after `target_db` in videx-db and save the table schema.
    for target_db, table_dict in meta_dict.items():
        videx_env.execute(f"DROP DATABASE IF EXISTS `{target_db}`")
        videx_env.execute(f"CREATE DATABASE `{target_db}`")

        # `videx_env` might need to create tables in multiple databases;
        # since DDL does not include db_name, switching is required.
        # However, it should revert to the default_db after execution.
        videx_default_db = videx_env.default_db
        try:
            videx_env.set_default_db(target_db)
            for table in table_dict.values():
                create_table_ddl = re.sub(r"ENGINE=\w+", "ENGINE={}".format(new_engine), table.ddl)
                # remove secondary index
                match = re.search(r'SECONDARY_ENGINE=(\w+)', create_table_ddl)
                if match:
                    value = match.group(1)
                    logging.warning(f"find SECONDARY_ENGINE={value}, remove it from CREATE TABLE DDL")
                    create_table_ddl = re.sub(r'SECONDARY_ENGINE=\w+', '', create_table_ddl)
                videx_env.execute(create_table_ddl)
        finally:
            videx_env.set_default_db(videx_default_db)

def create_videx_env_multi_db_for_pg(videx_env: Env,
                              meta_dict: dict,
                              new_engine: str = 'VIDEX',
                              ):
    for target_db, table_dict in meta_dict.items():
        #TODO: In Postgresql, you cannot drop a database if you are connecting on it. 
        # so we need to switch to another database first (Here we switch to 'postgres').
        videx_env._switch_db("postgres")
        videx_env.execute(f"DROP DATABASE IF EXISTS {target_db}")
        videx_env.execute(f"CREATE DATABASE {target_db}")
        videx_env._switch_db(target_db)
        videx_env.execute(f"CREATE EXTENSION VIDEX")
        videx_default_db = videx_env.default_db
        try:
            videx_env.set_default_db(target_db)
            print(f"taget_database: {target_db}, table_size: {len(table_dict)}")
            for table in table_dict.values():
                dump_text = table.ddl
                # replace engine from heap to videx before executing
                pattern = r'(CREATE TABLE\s+[\w\.]+\s*\(\s*.*?\s*\))\s*;'
                replacement = rf'\1 USING {new_engine};'
                videx_dump_text = re.sub(pattern, replacement, dump_text, flags=re.DOTALL)
                videx_env.execute(videx_dump_text)
        finally:
            videx_env.set_default_db(videx_default_db)

def post_to_clear_videx_server_cache(videx_server: str, task_ids: List[str]) -> Response:
    """Send a request to the specified server to clear the specified task IDs.

    Args:
        videx_server (str): ip:port
        task_ids (List[str]): list of task id

    Returns:
        _type_: _description_
    """
    resp = requests.post(f'http://{videx_server}/clear_cache',
                         data=json.dumps({"key_list": task_ids}).encode('utf-8'),
                         headers={'Content-Type': 'application/json'})
    return resp


def startup_videx_server(
        port=5001,
        VidexModelClass: Type[VidexModelBase] = VidexModelInnoDB,
        load_meta_by_task_id_func: Callable[[str], VidexDBTaskStats] = None,
        start_ip="0.0.0.0", debug=False,
        logging_package=videx_logging,
        **model_kwargs,
):
    """
    curl --location --request POST 'http://127.0.0.1:5000/ask_videx' \
    --header 'Content-Type: application/json' \
    --data-raw '{
        "item_type": "videx_root",
        "properties": {
            "dbname": "tpcc_videx",
            "function": "virtual double ha_videx::scan_time()",
            "table_name": "STOCK",
            "target_storage_engine": "INNODB"
        },
        "data": []
    }'

    curl --location --request POST 'http://127.0.0.1:5000/ask_videx' \
    --header 'Content-Type: application/json' \
    --data-raw '{
        "item_type": "videx_root",
        "properties": {
            "dbname": "tpcc_videx",
            "function": "virtual double ha_videx::get_memory_buffer_size()",
            "table_name": "STOCK",
            "target_storage_engine": "INNODB"
        },
        "data": []
    }'

    curl --location --request POST 'http://127.0.0.1:5000/ask_videx' \
    --header 'Content-Type: application/json' \
    --data-raw '{"item_type":"videx_request","properties":{"dbname":"tpcc","function":"virtual ha_rows ha_innobase::records_in_range(uint, key_range*, key_range*)","table_name":"ITEM","target_storage_engine":"INNODB"},"data":[{"item_type":"min_key","properties":{"index_name":"idx_I_IM_ID_I_PRICE","length":"7","operator":">"},"data":[{"item_type":"column_and_bound","properties":{"column":"I_IM_ID","value":"3"},"data":[]},{"item_type":"column_and_bound","properties":{"column":"I_PRICE","value":"2.00"},"data":[]}]},{"item_type":"max_key","properties":{"index_name":"idx_I_IM_ID_I_PRICE","length":"7","operator":">"},"data":[{"item_type":"column_and_bound","properties":{"column":"I_IM_ID","value":"3"},"data":[]},{"item_type":"column_and_bound","properties":{"column":"I_PRICE","value":"4.00"},"data":[]}]}]}'
    """
    global videx_meta_singleton
    videx_meta_singleton = VidexSingleton(
        VidexModelClass=VidexModelClass,
        load_meta_by_task_id_func=load_meta_by_task_id_func,
        logging_package=logging_package,
        **model_kwargs,
    )

    # Start the service.
    logging.info(f"\n{'- ' * 30}\n"
                 f"VIDEX statistic server has been started.\n"
                 f"Current ModelClass: {videx_meta_singleton.VidexModelClass.__name__}\n"
                 f"To use VIDEX, please set the following variables before explaining your SQL:\n"
                 f"SET @VIDEX_SERVER='{get_local_ip()}:{port}';\n"
                 f"{'- ' * 30}\n"
                 )

    app.run(debug=debug, threaded=True, host=start_ip, port=port, use_reloader=False)

