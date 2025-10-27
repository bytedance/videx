# -*- coding: utf-8 -*-
"""
Copyright (c) 2024 Bytedance Ltd. and/or its affiliates
SPDX-License-Identifier: MIT
"""
import copy
import json
import logging
import math
import os
import shutil
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import List, Dict, Tuple, Optional, Union, Any

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from sub_platforms.sql_opt.column_statastics.statistics_info import TableStatisticsInfo
from sub_platforms.sql_opt.common.db_variable import VariablesAboutIndex, DEFAULT_INNODB_PAGE_SIZE
from sub_platforms.sql_opt.common.exceptions import TraceLoadException
from sub_platforms.sql_opt.common.pydantic_utils import PydanticDataClassJsonMixin
from sub_platforms.sql_opt.common.sample_file_info import SampleFileInfo
from sub_platforms.sql_opt.databases.mysql.mysql_command import MySQLVersion
from sub_platforms.sql_opt.env.rds_env import Env
from sub_platforms.sql_opt.meta import Table, Column, Index
from sub_platforms.sql_opt.videx.common.estimate_stats_length import estimate_data_length
from sub_platforms.sql_opt.videx.videx_histogram import HistogramStats, generate_fetch_histogram
from sub_platforms.sql_opt.videx.videx_mysql_utils import _parse_col_names
from sub_platforms.sql_opt.videx.videx_utils import load_json_from_file, dump_json_to_file, GT_Table_Return, \
    target_env_available_for_videx

# VIDEX Statistic attribute keys
EXTRA_INFO_KEY_pct_cached = 'pct_cached'
EXTRA_INFO_KEY_use_gt = 'use_gt'
EXTRA_INFO_KEY_mulcol = 'mulcol'
EXTRA_INFO_KEY_gt_rec_in_ranges = 'gt_rec_in_ranges'
EXTRA_INFO_KEY_gt_req_resp = 'gt_req_resp'

# ############################################################################
# MySQL 8.0 Constant
# /root/mysql-server/storage/innobase/include/univ.i:325
# constexpr uint32_t UNIV_PAGE_SIZE_MIN = 1 << UNIV_PAGE_SIZE_SHIFT_MIN;
UNIV_PAGE_SIZE_SHIFT_DEF = 14
UNIV_PAGE_SIZE_DEF = 1 << UNIV_PAGE_SIZE_SHIFT_DEF

# #define IN_MEMORY_ESTIMATE_UNKNOWN -1.0
# /root/mysql-server/sql/key.h:110
IN_MEMORY_ESTIMATE_UNKNOWN = -1.0

# prefer to use cached pct from videx metadata
PCT_CACHED_MODE_PREFER_META = -1

IO_SIZE = 4096

# ############################################################################

INVALID_VALUE = -1234


class VidexDBTaskStats(BaseModel, PydanticDataClassJsonMixin):
    task_id: Optional[str]
    meta_dict: Dict[str, Dict[str, Table]]
    stats_dict: Dict[str, Dict[str, TableStatisticsInfo]]
    db_config: VariablesAboutIndex
    # use_gt: Optional[bool] = field(default=True)
    # gt_rec_in_ranges: Optional[List[Any]] = field(default_factory=list)
    # gt_req_resp: Optional[List[Any]] = field(default_factory=list)
    sample_file_info: Optional[SampleFileInfo] = Field(default=None)

    def model_post_init(self, __context: Any) -> None:
        self.meta_dict = {k.lower(): {k1.lower(): v1 for k1, v1 in v.items()} for k, v in self.meta_dict.items()}
        self.stats_dict = {k.lower(): {k1.lower(): v1 for k1, v1 in v.items()} for k, v in self.stats_dict.items()}

    def get_table_stats_info(self, db_name: str, table_name: str) -> Optional[TableStatisticsInfo]:
        db_name = db_name.lower()
        table_name = table_name.lower()
        return self.stats_dict.get(db_name, {}).get(table_name)

    def get_table_meta(self, db_name: str, table_name: str) -> Optional[Table]:
        db_name = db_name.lower()
        table_name = table_name.lower()
        return self.meta_dict.get(db_name, {}).get(table_name)

    def get_stats_info_keys(self) -> Dict[str, List[str]]:
        """
        return format: {'db1': ['tb1', 'tb2'], 'db2': ['tb3']} in stats_dict
        """
        return {db: list(sorted(db_stats.keys())) for db, db_stats in self.stats_dict.items()}

    def get_meta_info_keys(self) -> Dict[str, List[str]]:
        """
        return format: {'db1': ['tb1', 'tb2'], 'db2': ['tb3']} in meta_dict
        """
        return {db: list(sorted(db_meta.keys())) for db, db_meta in self.meta_dict.items()}

    def get_expect_response(self, req_json, result2str: bool = True):
        if isinstance(req_json, dict) or isinstance(req_json, list):
            req_json = json.dumps(req_json)
        # 临时性的，每个 db、每个 table 中填入的 resp 都一样，所以找到一个符合的就返回。
        # 根本原因是 req_json 实际上是 db task 级别的，不应该放入某个 db、某个 table
        for _, db_dict in self.stats_dict.items():
            for _, table_dict in db_dict.items():
                resp = (table_dict.extra_info.get(EXTRA_INFO_KEY_gt_req_resp) or {}).get(str(req_json))
                if resp is not None and result2str:
                    resp = {str(k): str(v) for k, v in resp.items()}
                return resp

    @property
    def key(self):
        return self.to_key(self.task_id)

    def key_is_none(self):
        return not self.task_id or self.task_id == 'None'

    @staticmethod
    def to_key(task_id: str) -> str:
        return f"{task_id}"

    def merge_with(self, other: 'VidexDBTaskStats', inplace: bool = False) -> Optional['VidexDBTaskStats']:
        # Check for essential matches
        if self.task_id != other.task_id or (
                self.sample_file_info and other.sample_file_info and (
                self.sample_file_info.local_path_prefix != other.sample_file_info.local_path_prefix or
                self.sample_file_info.tos_path_prefix != other.sample_file_info.tos_path_prefix
        )):
            return None

        target = self if inplace else copy.deepcopy(self)

        # Merge meta_dict
        for db, tables in other.meta_dict.items():
            if db not in target.meta_dict:
                target.meta_dict[db] = tables
            else:
                target.meta_dict[db].update(tables)

        # Merge stats_dict
        for db, tables in other.stats_dict.items():
            if db not in target.stats_dict:
                target.stats_dict[db] = tables
            else:
                target.stats_dict[db].update(tables)

        # Merge sample_file_info
        if self.sample_file_info and other.sample_file_info:
            merged_sample_file_dict = defaultdict(lambda: defaultdict(list))
            all_dbs = set(self.sample_file_info.sample_file_dict.keys()).union(
                other.sample_file_info.sample_file_dict.keys())
            for db in all_dbs:
                all_tables = set(self.sample_file_info.sample_file_dict.get(db, {}).keys()).union(
                    other.sample_file_info.sample_file_dict.get(db, {}).keys())
                for table in all_tables:
                    items = set(self.sample_file_info.sample_file_dict.get(db, {}).get(table, []))
                    items.update(other.sample_file_info.sample_file_dict.get(db, {}).get(table, []))
                    merged_sample_file_dict[db][table] = sorted(items)

            target.sample_file_info.sample_file_dict = dict(merged_sample_file_dict)

            # Optionally merge table_load_rows
            if self.sample_file_info.table_load_rows and other.sample_file_info.table_load_rows:
                target.sample_file_info.table_load_rows.update(other.sample_file_info.table_load_rows)

        return target


class VidexTableStats(BaseModel, PydanticDataClassJsonMixin):
    """
    Represents the statistics of a HA table.
    """
    dbname: str
    table_name: str

    data_file_length: int = 0  # Length of data file
    max_data_file_length: int = 0  # Maximum length of data file
    index_file_length: int = 0  # Length of index file

    # SHOW VARIABLES LIKE 'myisam_max_sort_file_size';
    # but myisam_max_sort_file_size = 9223372036853727232，slightly smaller than max_index_file_length
    max_index_file_length: int = 0  # Maximum length of index file
    delete_length: int = 0  # Free bytes
    auto_increment_value: int = 0  # Value for auto-increment column
    records: int = 0  # Number of records in the table, i.e table rows
    deleted: int = 0  # Number of deleted records
    mean_rec_length: int = 0  # Physical record length
    create_time: int = 0  # Time when the table was created
    check_time: int = 0  # Check time
    update_time: int = 0  # Update time

    # The concepts of blocks and pages are equivalent in InnoDB.
    # SHOW VARIABLES LIKE 'innodb_page_size';
    block_size: int = 0  # Index block size
    mrr_length_per_rec: int = 0  # Number of buffer bytes needed by native mrr implementation

    # Estimate for how much of the index is available in memory buffer
    # index_name -> {'page_type', 'pct_cached', 'pool_rows'}
    pct_cached: Dict[str, dict] = Field(default_factory=dict)
    # SHOW VARIABLES LIKE 'innodb_buffer_pool_size';
    innodb_buffer_pool_size: int = INVALID_VALUE

    data_free_length: int = 0
    # from mysql.innodb_table_stats
    clustered_index_size: int = INVALID_VALUE
    sum_of_other_index_sizes: int = INVALID_VALUE

    # innodb part, god view
    UNIV_PAGE_SIZE: int = INVALID_VALUE

    hist_columns: Dict[str, HistogramStats] = Field(default_factory=dict)
    # Refer to VidexDBTaskStats.sample_file_info, calculate ndv based on sampling data
    sample_file_info: Optional[SampleFileInfo] = Field(default=None)
    """
    column->ndv
    """
    ndvs_single: Dict[str, int] = Field(default_factory=dict)
    """
    index_name -> field -> {}
    Note that in real scenarios, the following multi-column ndvs needs to be predicted, not directly obtained.

            "PRIMARY": {
                "S_W_ID": {
                    "stat_name": "n_diff_pfx01",
                    "stat_value": 7,
                    "sample_size": 9,
                    "stat_description": "S_W_ID",
                    "n_field": 1
                },
                "S_I_ID": {
                    "stat_name": "n_diff_pfx02",
                    "stat_value": 782180,
                    "sample_size": 20,
                    "stat_description": "S_W_ID,S_I_ID",
                    "n_field": 2
                }
            }
    """
    ndvs_multi_col_gt: Dict[str, Dict[str, dict]] = Field(default_factory=dict)
    # index_name -> range_str -> rows
    gt_return: GT_Table_Return = None

    # records metadata about table schema
    table_meta: Optional[Table] = None

    def get_col_hist(self, col: str) -> Optional[HistogramStats]:
        return self.hist_columns.get(col)

    def get_ideal_ndv(self, raw_index_name: str, raw_first_columns: List[str]) -> int:
        index_name = raw_index_name.lower()
        last_field = raw_first_columns[-1]
        if index_name not in self.ndvs_multi_col_gt or last_field not in self.ndvs_multi_col_gt[index_name]:
            logging.info(
                f"NOGT: not found ideal_rec_per_key for table={self.table_name}, "
                f"index={raw_index_name}, "
                f"cols={raw_first_columns}")
            return None
        ndv = self.ndvs_multi_col_gt[index_name][last_field]
        if ','.join(raw_first_columns).lower() != ndv['stat_description'].lower():
            logging.warning(
                f"NOGT: to find ideal_rec_per_key for table={self.table_name}, index={raw_index_name}, "
                f"but input cols={raw_first_columns} != data {ndv['stat_description']}")
            return None
        res = ndv['stat_value']
        logging.info(f"FOUND GT: ideal_rec_per_key for table={self.table_name}, index={raw_index_name}, "
                     f"cols={raw_first_columns}, ndv = {res}")
        return res

    @staticmethod
    def from_json(dbname: str, table_name: str, raw_meta_dict: Table,
                  hist_columns: Dict[str, HistogramStats],
                  sample_file_info: Optional[SampleFileInfo],
                  db_config: VariablesAboutIndex,
                  ideal_ndvs: dict, single_ndvs: dict,
                  pct_cached: dict,
                  gt_rec_in_ranges: GT_Table_Return):
        """
        Args:
            dbname:
            table_name:
            raw_meta_dict:
            ideal_ndvs:
            gt_rec_in_ranges: index_name -> range_str -> rows

        Returns:

        """
        # index lowercase
        hist_columns = {col: None if not hist else HistogramStats.from_dict(hist) for col, hist in
                        hist_columns.items()}
        ideal_ndvs = {index_name.lower(): {col: gt_rec for col, gt_rec in ideal_ndvs[index_name].items()} for
                      index_name in (ideal_ndvs or {})}
        single_ndvs = {col: int(math.ceil(ndv)) for col, ndv in single_ndvs.items()}
        innodb_page_size = int(
            db_config.innodb_page_size.value) if db_config.innodb_page_size.value is not None else DEFAULT_INNODB_PAGE_SIZE

        raw_meta_dict = copy.deepcopy(raw_meta_dict) # not affect raw data

        if raw_meta_dict.data_length is None:
            if raw_meta_dict.table_size is None:
                raise Exception(f"All stats about table size is None, including table_size, data_length")
            try:
                res = estimate_data_length(raw_meta_dict, fix_row_overhead=10, consider_delete=True,
                                           data_free_coefficient=0.1)
                logging.info(f"Miss data_length, estimate for {table_name}: {res}")
                raw_meta_dict.data_length = res["combined_estimate"]
                raw_meta_dict.avg_row_length = res["avg_row_length"]
                raw_meta_dict.data_free = res["data_free"]
            except Exception as e:
                logging.error(f"data_length is None, estimate_data_length meet errors: {e}")
                raw_meta_dict.data_length = raw_meta_dict.table_size * 0.9

        if raw_meta_dict.cluster_index_size is None:
            raw_meta_dict.cluster_index_size = int(raw_meta_dict.data_length / innodb_page_size)

        res = VidexTableStats(
            dbname=dbname,
            table_name=table_name,
            data_file_length=raw_meta_dict.data_length,
            max_data_file_length=raw_meta_dict.data_length,
            index_file_length=int(raw_meta_dict.index_length) if raw_meta_dict.index_length is not None else 0,
            records=int(raw_meta_dict.rows),
            mean_rec_length=int(raw_meta_dict.avg_row_length) if raw_meta_dict.avg_row_length is not None else 0,

            # SHOW VARIABLES LIKE 'innodb_page_size';
            block_size=innodb_page_size,
            # SHOW VARIABLES LIKE 'myisam_max_sort_file_size';
            max_index_file_length=int(
                db_config.myisam_max_sort_file_size.value) if db_config.myisam_max_sort_file_size.value else 0,
            # SHOW VARIABLES LIKE 'innodb_buffer_pool_size';
            innodb_buffer_pool_size=int(
                db_config.innodb_buffer_pool_size.value) if db_config.innodb_buffer_pool_size.value else 4 * 1024 * 1024 * 1024,
            pct_cached=pct_cached or {},
            data_free_length=int(raw_meta_dict.data_free) if raw_meta_dict.data_free is not None else 0,

            # innodb_stats
            clustered_index_size=raw_meta_dict.cluster_index_size,
            sum_of_other_index_sizes=raw_meta_dict.other_index_sizes if raw_meta_dict.other_index_sizes is not None else int(
                raw_meta_dict.index_length / innodb_page_size) if raw_meta_dict.index_length is not None else 0,
            UNIV_PAGE_SIZE=UNIV_PAGE_SIZE_DEF,
            hist_columns=hist_columns,
            sample_file_info=sample_file_info,
            ndvs_single=single_ndvs,
            ndvs_multi_col_gt=ideal_ndvs,
            gt_return=gt_rec_in_ranges,
            table_meta=raw_meta_dict,
        )
        # for k, v in res.hist_columns.items():
        #     if v is not None:
        #         v.table_rows = int(raw_meta_dict.rows)
        return res


def fetch_ndv_multi_col_gt(env: Env, dbname: str, table_name: str = None) -> Dict[str, Dict[str, Dict[str, dict]]]:
    """
    获取某个表上所有已创建索引的 rec_per_key。实际上就是获取多列的 ndv。
    Args:
        env:
        dbname:
        table_name: 如果指定了表名，就只获取这个表的索引信息，否则就获取所有表的索引信息

    Returns:
        lower_table_name -> index_name -> column_name -> n_diff gt

    """
    if not target_env_available_for_videx(env):
        raise Exception(f"given env ({env.instance=}) is not in BLACKLIST, cannot fetch_ndv_multi_col_gt directly")

    sql = f"select database_name,table_name,index_name,stat_name,stat_value,sample_size,stat_description " \
          f"from mysql.innodb_index_stats " \
          f"where database_name='{dbname}' and stat_name like 'n_diff%'"
    if table_name:
        sql += f" and table_name = '{table_name}' "
    df_res = env.query_for_dataframe(sql)

    res = defaultdict(lambda: defaultdict(dict))

    for (table_name, index_name), df_index in df_res.groupby(['table_name', 'index_name']):
        df_index.sort_values(by=['stat_name'], inplace=True)
        for idx, row in df_index.iterrows():
            fields = row['stat_description'].split(',')
            last_field = fields[-1]
            res[table_name.lower()][index_name][last_field] = {
                'stat_name': row['stat_name'],
                'stat_value': row['stat_value'],
                'sample_size': row['sample_size'],
                'stat_description': row['stat_description'],
                'n_field': len(fields)
            }

    return res


def fetch_ndv_single(env: Env, target_db: str, all_table_names: List[str]) \
        -> Dict[str, Dict[str, Dict[str, HistogramStats]]]:
    if not target_env_available_for_videx(env):
        raise Exception(f"given env ({env.instance=}) is not in BLACKLIST, cannot fetch_ndv_single directly")

    res_tables = defaultdict(dict)
    for table_name in all_table_names:
        table_meta: Table = env.get_table_meta(target_db, table_name)
        for c_id, col in enumerate(table_meta.columns):
            col: Column
            sql = f"SELECT COUNT(DISTINCT {col.name}) FROM `{target_db}`.`{table_name}`;"
            logging.info(f"fetch NDV for {table_name}.{col} [{c_id}/{len(table_meta.columns)}]: {sql}")
            try:
                ndv = env.execute(sql, params=None)
            except Exception as e:
                logging.error(f"fetch NDV error on {target_db}.{table_name}.{col}: {e}")
                ndv = INVALID_VALUE

            res_tables[str(table_name).lower()][col.name] = int(np.squeeze(ndv))
    return res_tables


def fetch_information_schema(env: Env, target_dbname: str) -> Dict[str, dict]:
    """
    fetch metadata
    Args:
        env:
        target_dbname:

    Returns:
        lower table -> rows (to construct VidexTableStats), 不包含 db 层

    """
    if not target_env_available_for_videx(env):
        raise Exception(f"given env ({env.instance=}) is not in BLACKLIST, cannot fetch raw metadata directly")

    global_var_keys = ['innodb_page_size', 'myisam_max_sort_file_size', 'innodb_buffer_pool_size']
    global_var_dict = {}
    for key in global_var_keys:
        sql = f"SHOW VARIABLES LIKE '{key}';"
        tmp_ = env.execute(sql, params=None)
        global_var_dict[key] = int(tmp_[0][1])

    # part 1: basic
    sql = """
        SELECT TABLE_CATALOG, TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE, ENGINE, 
               VERSION, ROW_FORMAT, TABLE_ROWS, AVG_ROW_LENGTH, DATA_LENGTH, 
               MAX_DATA_LENGTH, INDEX_LENGTH, DATA_FREE, AUTO_INCREMENT, 
               CREATE_TIME, UPDATE_TIME, CHECK_TIME, TABLE_COLLATION, 
               CHECKSUM, CREATE_OPTIONS, TABLE_COMMENT 
        FROM information_schema.TABLES 
        WHERE table_schema = '%s'
          AND ENGINE = 'InnoDB'
          AND TABLE_TYPE = 'BASE TABLE'
    """ % target_dbname

    basic_list: pd.DataFrame = env.query_for_dataframe(sql).to_dict(orient='records')
    res_dict = {}

    # Convert datetime objects to unix timestamp
    for row in basic_list:
        for key in ['CREATE_TIME', 'UPDATE_TIME', 'CHECK_TIME']:
            if not pd.isna(row[key]):
                row[key] = int(row[key].timestamp())
            else:
                row[key] = None
        row.update(global_var_dict)
        table_name = str(row["TABLE_NAME"]).lower()
        res_dict[table_name] = row

        table_obj: Table = env.get_table_meta(target_dbname, row["TABLE_NAME"])
        res_dict[table_name]['columns'] = [json.loads(c.to_json()) for c in table_obj.columns]
        res_dict[table_name]['indexes'] = [json.loads(i.to_json()) for i in table_obj.indexes]
    # print(json.dumps(res_dict, indent=4))

    # part 2: innodb_table_stats
    sql = """
        select TABLE_NAME, N_ROWS,CLUSTERED_INDEX_SIZE, SUM_OF_OTHER_INDEX_SIZES 
        from `mysql`.`innodb_table_stats` where database_name='%s';
    """ % target_dbname
    innodb_table_stats_list = env.query_for_dataframe(sql).to_dict(orient='records')
    for row in innodb_table_stats_list:
        table_name = str(row["TABLE_NAME"]).lower()
        if table_name not in res_dict:
            print(table_name, 'not found in res_dict')
        else:
            res_dict[table_name].update(row)

    # part 3: table_in_mem_estimate
    sql = """
        SELECT 
          its.database_name as db_name,
          its.table_name as table_name,
          its.index_name as index_name,
          COALESCE(ibp.PAGE_TYPE, 'INDEX_NOSTATS') as page_type,
          COALESCE(ibp.records, 0) as pool_rows,
          its.n_rows as total_rows,
          COALESCE(ibp.records, 0)/its.n_rows AS pct_cached,
          COALESCE(ibp.n_pages, 0)/its.n_leaf_pages AS page_pct_cached
        FROM 
          (
            SELECT DISTINCT
              database_name,
              table_name,
              index_name,
              CONCAT('`', database_name, '`.`', table_name, '`') AS full_table_name, 
              n_leaf_pages,
              n_rows
            FROM 
              mysql.innodb_table_stats
            join (
                select database_name,table_name,index_name,
                max(stat_value) as n_leaf_pages 
                from mysql.innodb_index_stats 
                where stat_name='n_leaf_pages'
                group by database_name,table_name,index_name
            ) t_pages
            using (database_name, table_name)
            WHERE 
              database_name = '{}'
          ) its
        LEFT JOIN 
          (
            SELECT 
              TABLE_NAME,
              INDEX_NAME,
              PAGE_TYPE, 
              SUM(NUMBER_RECORDS) AS records,
              COUNT(PAGE_NUMBER) AS n_pages
            FROM 
              INFORMATION_SCHEMA.INNODB_BUFFER_PAGE
            WHERE 
              TABLE_NAME LIKE '%`{}`%'
            GROUP BY 
              TABLE_NAME, INDEX_NAME, PAGE_TYPE
          ) ibp 
        ON 
          its.full_table_name = ibp.TABLE_NAME and its.index_name = ibp.INDEX_NAME
        ORDER BY table_name, index_name;
    """.format(target_dbname, target_dbname)

    data_table_in_mem: pd.DataFrame = env.query_for_dataframe(sql)

    for (db_name, table_name,), df_table in data_table_in_mem.groupby(['db_name', 'table_name']):
        table_name = str(table_name).lower()
        if table_name not in res_dict:
            logging.warning(table_name, 'not found in data_table_in_mem')
        else:
            _dict = {}
            for idx, row in df_table.iterrows():
                if pd.isna(row['pct_cached']):
                    pct = 0
                else:
                    pct = max(0., min(float(row['pct_cached']), 1.))
                _dict[row['index_name']] = {
                    'page_type': row['page_type'],
                    'pct_cached': pct,
                    'pool_rows': float(row['pool_rows']),
                }
            res_dict[table_name]['pct_cached'] = _dict

    # part 4:  obtain ddl
    for t, table_dict in res_dict.items():
        table: Table = env.get_table_meta(target_dbname, table_dict['TABLE_NAME'])
        table_dict['DDL'] = table.ddl

    # make sure lower case
    res_dict = {k.lower(): v for k, v in res_dict.items()}
    return res_dict


def fetch_all_meta_for_videx(env: Env, target_db: str, all_table_names: List[str] = None,
                             result_dir: str = None,
                             n_buckets=64,
                             hist_force: bool = False,
                             drop_hist_after_fetch: bool = True,
                             hist_mem_size: int = None,
                             histogram_data: dict = None,
                             ) -> Tuple[dict, dict, dict, dict]:
    """

    Args:
        env: mysql 连接对象
        target_db: 目标库名
        result_dir: 结果保存的路径，如果为None则不保存结果到文件，仅返回dict
        n_buckets: 直方图的桶数量
        hist_force: 是否强制重新计算直方图，如果为True则会重新计算，否则会读取已有的直方图结果
        drop_hist_after_fetch: 为了避免hist 对 videx 的干扰，获取 hist 之后 drop histogram
        histogram_data: 如果非空，则不直接采集直方图，而是直接使用传入的 histogram_data

    Returns:
        如果 result_dir 为 None，返回四部分 metadata dict，否则保存到文件下，返回文件路径：
            - info_stats_dict：表行数、data file length 等等
            - hist_dict：单列直方图
            - ndv_dict：单列 ndv 信息。所有表、所有列的 ndv 我们都可以拿到
            - ndv_mulcol_dict：多列 ndv。多列 ndv 的信息来自于已经创建的复合索引

    """
    if not target_env_available_for_videx(env):
        raise Exception(f"given env ({env.instance=}) is not in BLACKLIST, cannot fetch raw metadata directly")
    # 如果非空，则将数据写入到指定目录的文件中
    logging.info(
        f"fetch_all_meta_for_videx. {target_db=} {result_dir=} {n_buckets=} {hist_force=} {hist_mem_size=} {all_table_names=}")
    stats_file = f'videx_{target_db}_info_stats.json'
    hist_file = f'videx_{target_db}_histogram.json'
    ndv_single_file = f'videx_{target_db}_ndv_single.json'
    ndv_mulcol_file = f'videx_{target_db}_ndv_mulcol.json'

    # 直接抓取 stats_dict
    if result_dir is not None and os.path.exists(os.path.join(result_dir, stats_file)):
        stats_dict = load_json_from_file(os.path.join(result_dir, stats_file))
    else:
        stats_dict = fetch_information_schema(env, target_db)

    if all_table_names is None or len(all_table_names) == 0:
        all_table_names = list(stats_dict.keys())
    else:
        stats_dict = {k: v for k, v in stats_dict.items() if k.lower() in set(t.lower() for t in all_table_names)}

    # >>>>>>>>>>>>>>>> ndv_single_dict >>>>>>>>>>>>>
    if result_dir is not None and os.path.exists(os.path.join(result_dir, ndv_single_file)):
        ndv_single_dict = load_json_from_file(os.path.join(result_dir, ndv_single_file))
    else:
        ndv_single_dict = {}
    miss_ndv_tables = sorted(t for t in all_table_names if t.lower() not in set(s.lower() for s in ndv_single_dict))
    if len(miss_ndv_tables) > 0:
        logging.info(f"fetch meta for videx: {ndv_single_file = } not found in {result_dir = }, or exist ndv single "
                     f"is not enough.fetch it: {sorted(ndv_single_dict.keys()) = } {miss_ndv_tables=}")
        tmp_ndv_single_dict = fetch_ndv_single(env, target_db, miss_ndv_tables)
        ndv_single_dict.update(tmp_ndv_single_dict)

    # <<<<<<<<<<<<<<< ndv_single_dict end <<<<<<<<<<<<<<<<

    # >>>>>>>>>>>>>>>> his_dict >>>>>>>>>>>>>
    if histogram_data:
        hist_dict = histogram_data.get(target_db)
        if not hist_dict:
            logging.warning(f"{target_db=} not in {histogram_data.keys()=}")
            hist_dict = {}
        else:
            logging.info("exists pass-in histogram dict, not generate or load json")
    # 以下两者生成的耗时很久。但同时，不随着 index 改变而改变，因此仅当 result 为空或路径不存在时才重新生成
    elif result_dir is not None and os.path.exists(os.path.join(result_dir, hist_file)):
        hist_dict = load_json_from_file(os.path.join(result_dir, hist_file))
    else:
        hist_dict = {}
    miss_hist_tables = sorted(t for t in all_table_names if t.lower() not in set(s.lower() for s in hist_dict))
    if len(miss_hist_tables) > 0:
        logging.info(f"fetch meta for videx: {hist_file=} not found in {result_dir=}, or exist hist is not enough."
                     f"fetch it. {sorted(hist_dict.keys())=} {miss_hist_tables=}")
        tmp_hist_dict = generate_fetch_histogram(env, target_db, miss_hist_tables,
                                                 n_buckets=n_buckets,
                                                 force=hist_force,
                                                 drop_hist_after_fetch=drop_hist_after_fetch,
                                                 ret_json=True,
                                                 hist_mem_size=hist_mem_size,
                                                 ndv_single_dict=ndv_single_dict,
                                                 )
        hist_dict.update(tmp_hist_dict)

    # <<<<<<<<<<<<<<< hist dict end <<<<<<<<<<<<<<<<

    # >>>>>>>>>>>>>>>> ndv_mulcol_dict >>>>>>>>>>>>>
    if result_dir is not None and os.path.exists(os.path.join(result_dir, ndv_mulcol_file)):
        ndv_mulcol_dict = load_json_from_file(os.path.join(result_dir, ndv_mulcol_file))
    else:
        ndv_mulcol_dict = fetch_ndv_multi_col_gt(env, target_db)
    # <<<<<<<<<<<<<<< ndv_mulcol_dict end <<<<<<<<<<<<<<<<

    logging.info(f"fetch result: {all_table_names=}, {result_dir=}")
    logging.info(f"fetch result: {sorted(hist_dict.keys())=}")
    logging.info(f"fetch result: {sorted(ndv_single_dict.keys())=}")
    logging.info(f"fetch result: {sorted(ndv_mulcol_dict.keys())=}")

    # 如果 result_dir 非空，则额外写出到文件
    if result_dir is not None:
        # 如果非空，则将数据写入到指定目录的文件中
        os.makedirs(result_dir, exist_ok=True)

        dump_json_to_file(os.path.join(result_dir, stats_file), stats_dict)
        # 仅当文件夹存在，但是文件不存在时才写入
        if miss_hist_tables:
            dump_json_to_file(os.path.join(result_dir, hist_file), hist_dict)
        # 仅当文件夹存在，但是文件不存在时才写入
        if miss_ndv_tables:
            dump_json_to_file(os.path.join(result_dir, ndv_single_file), ndv_single_dict)
        dump_json_to_file(os.path.join(result_dir, ndv_mulcol_file), ndv_mulcol_dict)

    return stats_dict, hist_dict, ndv_single_dict, ndv_mulcol_dict


def fetch_all_meta_with_one_file(meta_path: Union[str, dict],
                                 env: Env, target_db: str, all_table_names: List[str] = None,
                                 n_buckets=64,
                                 hist_force: bool = False,
                                 drop_hist_after_fetch: bool = True,
                                 hist_mem_size: int = None,
                                 histogram_data: dict = None,
                                 ) -> Tuple[dict, dict, dict, dict]:
    """Fetch all metadata and store/load it in a single file.

    This function provides a convenient way to handle metadata by either:
    1. Extracting metadata from an existing dictionary
    2. Loading metadata from an existing file
    3. Generating new metadata and saving it to a file

    Args:
        meta_path: Path to metadata file or metadata dictionary
        env: Environment configuration object
        target_db: Target database name
        all_table_names: List of table names to process
        n_buckets: Number of buckets for histogram
        hist_force: Force histogram regeneration
        drop_hist_after_fetch: Whether to drop histogram data after fetching
        hist_mem_size: Memory size limit for histogram
        histogram_data: Existing histogram data

    Returns:
        Tuple of (stats_dict, hist_dict, ndv_single_dict, ndv_mulcol_dict)
        - stats_dict: Statistics dictionary
        - hist_dict: Histogram dictionary
        - ndv_single_dict: Single column NDV dictionary
        - ndv_mulcol_dict: Multi-column NDV dictionary

    Raises:
        ValueError: If metadata_file is neither a dict nor a string path
    """

    # Handle dictionary input directly
    if isinstance(meta_path, dict):
        # Extract all required dictionaries from the metadata
        stats_dict = meta_path.get('stats_dict', {})
        hist_dict = meta_path.get('hist_dict', {})
        ndv_single_dict = meta_path.get('ndv_single_dict', {})
        ndv_mulcol_dict = meta_path.get('ndv_mulcol_dict', {})
        return stats_dict, hist_dict, ndv_single_dict, ndv_mulcol_dict

    # Reuse exists file only if specifying meta_path and the path exists
    if meta_path is not None and isinstance(meta_path, str) and os.path.exists(meta_path):
        # Load existing metadata file if it exists
        metadata = load_json_from_file(meta_path)
        # Recursively process the loaded dictionary
        return fetch_all_meta_with_one_file(metadata, env, target_db, all_table_names,
                                            n_buckets, hist_force, drop_hist_after_fetch,
                                            hist_mem_size, histogram_data)

    # Generate new metadata if file is None, or file doesn't exist
    # Create temporary directory with timestamp
    temp_dir = f"temp_meta_{int(time.time())}"
    os.makedirs(temp_dir, exist_ok=True)

    try:
        # Fetch all metadata components using the core function
        stats_dict, hist_dict, ndv_single_dict, ndv_mulcol_dict = fetch_all_meta_for_videx(
            env, target_db, all_table_names,
            result_dir=temp_dir,
            n_buckets=n_buckets,
            hist_force=hist_force,
            drop_hist_after_fetch=drop_hist_after_fetch,
            hist_mem_size=hist_mem_size,
            histogram_data=histogram_data
        )

        if isinstance(meta_path, str):
            # If specify meta_path, combine all metadata components into a single dictionary and save to file
            metadata = {
                'stats_dict': stats_dict,
                'hist_dict': hist_dict,
                'ndv_single_dict': ndv_single_dict,
                'ndv_mulcol_dict': ndv_mulcol_dict
            }

            # Save combined metadata to file
            dump_json_to_file(meta_path, metadata)

        return stats_dict, hist_dict, ndv_single_dict, ndv_mulcol_dict

    finally:
        # Clean up temporary directory regardless of success/failure
        shutil.rmtree(temp_dir)


def _extract_range_rows_gt_from_trace_dict(join_opt) -> List[dict]:
    # 解析
    # 获取 join_opt['steps']
    join_opt = list(
        item.get('join_optimization') for item in join_opt.get("steps", []) if 'join_optimization' in item.keys())
    rows_estimation = list(item.get('rows_estimation') for opt in join_opt for item in opt.get("steps", []) if
                           'rows_estimation' in item.keys())
    range_analysis = list(
        [item.get('table'), item.get('range_analysis')] for opt in rows_estimation for item in opt if
        'range_analysis' in item.keys())
    res = []
    for table, opt in range_analysis:
        for item in opt.get('analyzing_range_alternatives', {}).get('range_scan_alternatives', []):
            item['table'] = table
            res.append(item)
    return res


def execute_sql_to_videx(sql: str, env: Env, videx_py_ip_port: str, videx_options: dict, strict_mode: bool = True,
                         skip_http: bool = False):
    """
    向 videx 发送一条指令。不记录 trace，但需要设置 videx ip port 和 options，目前适用于 create index ddl
    Args:
        sql:
        env:
        videx_py_ip_port:
        videx_options:
        strict_mode:

    Returns:

    """
    videx_options = json.dumps(videx_options)
    if strict_mode:
        if videx_py_ip_port is None:
            raise ValueError(f"videx_py_ip_port cannot be None")
        if not videx_options or 'task_id' not in videx_options:
            raise Exception(f"VIDEX options misses task_id: {videx_options=}")

    conn = env.mysql_util.get_connection()

    with conn.cursor() as cursor:
        if skip_http:
            cursor.execute(f"SET @DEBUG_SKIP_HTTP='True';")
            logging.info(f"SET @DEBUG_SKIP_HTTP='True';")
        else:
            cursor.execute(f"SET @VIDEX_SERVER='{videx_py_ip_port}';")
            logging.info(f"SET @VIDEX_SERVER='{videx_py_ip_port}';")
            cursor.execute(f"SET @VIDEX_OPTIONS='{videx_options}';")
            logging.info(f"SET @VIDEX_OPTIONS='{videx_options}';")
        try:
            logging.info(f"videx execute {sql=}")
            cursor.execute(sql, None)
            col_names = _parse_col_names(cursor)
            data = cursor.fetchall()
            data = list(map(list, data))
            df_res = pd.DataFrame(data, columns=col_names)
        except Exception as e:
            logging.error(f"execute explain meet error {sql=} : err={e}")
            df_res = None

    return df_res


def extract_rec_in_range_gt_from_explain(env: Env, sql: str,
                                         target_version: MySQLVersion=MySQLVersion.MySQL_8 or MySQLVersion.MariaDB_11_8,
                                         videx_py_ip_port: str = None, videx_options: dict = None,
                                         ret_trace: bool = True,
                                         verbose: bool = True,
                                         need_set_trace: bool = True,
                                         ) -> Tuple[pd.DataFrame, Optional[dict], Optional[List[dict]]]:
    """
    Conduct explain range_rows

    Returns:
        explain_result, trace_result, rec_in_range_gt

    """
    assert hasattr(env, "mysql_util"), f"env must has 'mysql_util'. maybe it's not RdsEnv or OpenEnv. type={type(env)}"
    sql = sql.strip()
    if not sql.lower().startswith("explain"):
        sql = 'EXPLAIN ' + sql
    conn = env.mysql_util.get_connection()
    with conn.cursor() as cursor:
        if ret_trace and need_set_trace:
            # turn on optimizer_trace
            cursor.execute('SET SESSION optimizer_trace="enabled=on", SESSION optimizer_trace_max_mem_size=4294967295;')
        if videx_py_ip_port is not None and videx_py_ip_port != '127.0.0.1:5001':
            # '127.0.0.1:5001' is default value in VIDEX engine.
            cursor.execute(f"SET @VIDEX_SERVER='{videx_py_ip_port}';")
            if verbose:
                logging.info(f"SET @VIDEX_SERVER='{videx_py_ip_port}';")
        if videx_options is not None:
            videx_options = json.dumps(videx_options)
            cursor.execute(f"SET @VIDEX_OPTIONS='{videx_options}';")
            if verbose:
                logging.info(f"SET @VIDEX_OPTIONS='{videx_options}';")
        if target_version == MySQLVersion.MySQL_57:
            optimizer_switch = ("SESSION optimizer_switch='subquery_to_derived=off,block_nested_loop=on,hash_join=off,"
                                "semijoin=off,firstmatch=off,loosescan=off,duplicateweedout=off,materialization=off';")
            cursor.execute(f"SET {optimizer_switch}")
        try:
            if verbose:
                logging.info(f"videx explain: {sql=}")
            st = time.perf_counter()
            cursor.execute(sql, None)
            col_names = _parse_col_names(cursor)
            data = cursor.fetchall()
            data = list(map(list, data))
            df_explain = pd.DataFrame(data, columns=col_names)
            if verbose:
                logging.info(f"videx explain use {time.perf_counter() - st:.3f} s")
        except Exception as e:
            logging.error(f"execute explain meet error {sql=}: err={e}")
            df_explain = pd.DataFrame({
                "code": [e.args[0]],
                "message": [str(e.args[1])],
                "type": [str(e.__class__.__name__)]
            })
        if ret_trace:
            # SELECT JSON_UNQUOTE(JSON_EXTRACT(JSON_EXTRACT(trace, '$.steps[*].lex_json_after_optimize'), '$[0]'))
            # FROM INFORMATION_SCHEMA.OPTIMIZER_TRACE;
            cursor.execute("SELECT trace FROM INFORMATION_SCHEMA.OPTIMIZER_TRACE;")
            data = cursor.fetchone()
        conn.commit()

    if data is None or len(data) < 1:
        return None, None, None

    if not ret_trace:
        return df_explain, None, None

    try:
        trace_dict = json.loads(data[0])
    except ValueError as e:
        raise TraceLoadException(e)

    return df_explain, trace_dict, _extract_range_rows_gt_from_trace_dict(trace_dict),


def meta_dict_to_sample_file(
        stats_dict,
        hist_dict,
        ndv_single_dict,
        multi_ndv_dict,
        gt_rec_in_ranges,
        gt_req_resp) -> Tuple[Dict[str, Dict[str, TableStatisticsInfo]], SampleFileInfo]:
    """
    construct TableStatisticsInfo and SampleFileInfo from a list of metadata statistic dict.
    """

    def to_lower_db_tb(d):
        return {k.lower(): {k2.lower(): v2 for k2, v2 in v.items()} for k, v in d.items()}

    # 将 db name 和 table name转为小写，其他 col、index_name 保持不变
    stats_dict = to_lower_db_tb(stats_dict)
    hist_dict = to_lower_db_tb(hist_dict)
    ndv_single_dict = to_lower_db_tb(ndv_single_dict)
    multi_ndv_dict = to_lower_db_tb(multi_ndv_dict or {})

    numerical_info: Dict[str, Dict[str, TableStatisticsInfo]] = defaultdict(dict)
    for db_name, db_stats_dict in stats_dict.items():
        for table_name, table_raw_stat_dict in db_stats_dict.items():
            # table_raw_stat_dict: Dict[str, Any] = self.stats_dict.get(db_name, {}).get(table_name, {})
            table_stat_info = TableStatisticsInfo(db_name=db_name, table_name=table_name)

            table_stat_info.ndv_dict = ndv_single_dict[db_name][table_name]

            histogram_data = hist_dict[db_name][table_name]
            if histogram_data and isinstance(list(histogram_data.values())[0], dict):
                # if histogram_dict is a dict, convert it to HistogramStats object
                histogram_data = {
                    col: HistogramStats.from_dict(hist_data) if hist_data else None
                    for col, hist_data in histogram_data.items()
                }
            table_stat_info.histogram_dict = histogram_data

            table_stat_info.not_null_ratio_dict = None  # to full it later if required
            # if 'TABLE_ROWS' not in table_raw_stat_dict:
            #     print()
            table_stat_info.num_of_rows = int(table_raw_stat_dict['TABLE_ROWS'])
            table_stat_info.sample_rows = None
            table_stat_info.is_sample_success = True
            table_stat_info.sample_file_list = None
            table_stat_info.block_size_list = None

            table_stat_info.extra_info = {
                # EXTRA_INFO_KEY_use_gt: self.use_gt,
                EXTRA_INFO_KEY_mulcol: multi_ndv_dict.get(db_name, {}).get(table_name),
                EXTRA_INFO_KEY_pct_cached: table_raw_stat_dict.get("pct_cached"),
                # 作为测试性的内容，我们只能将 gt_rec_in_ranges 和 gt_req_resp 重复的放到每一个 table 中
                EXTRA_INFO_KEY_gt_rec_in_ranges: gt_rec_in_ranges.get(db_name, []),
                EXTRA_INFO_KEY_gt_req_resp: gt_req_resp.get(db_name, {}),

            }

            numerical_info[db_name.lower()][table_name.lower()] = table_stat_info

    return numerical_info, SampleFileInfo(local_path_prefix='RowFetchNone', tos_path_prefix='RowFetchNone',
                                          sample_file_dict={}, )


def construct_videx_task_meta_from_local_files(task_id, videx_db,
                                               stats_file: Union[str, dict],
                                               hist_file: Union[str, dict],
                                               ndv_single_file: Union[str, dict],
                                               ndv_mulcol_file: Union[str, dict] = None,
                                               gt_rec_in_ranges_file: Union[str, dict] = None,
                                               gt_req_resp_file: Union[str, dict] = None,
                                               raise_error: bool = False,
                                               ) -> VidexDBTaskStats:
    """
    Add task metadata from a local file.
    Args:
        task_id:
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
    if isinstance(stats_file, dict):
        stats_dict = stats_file
    else:
        if not os.path.exists(stats_file):
            err_msg = f"stats_file not exists: {stats_file}, return"
            if raise_error:
                raise Exception(err_msg)
            logging.error(err_msg)
            return False
        stats_dict = load_json_from_file(stats_file)

    if isinstance(hist_file, dict):
        hist_dict = hist_file
    else:
        if not os.path.exists(hist_file):
            err_msg = f"hist_file not valid: {hist_file}, return"
            if raise_error:
                raise Exception(err_msg)
            logging.error(err_msg)
            return False
        hist_dict = load_json_from_file(hist_file)

    if isinstance(ndv_single_file, dict):
        ndv_single_dict = ndv_single_file
    else:
        if not os.path.exists(ndv_single_file):
            err_msg = f"ndv_single_file not valid: {ndv_single_file}, return"
            if raise_error:
                raise Exception(err_msg)
            logging.error(err_msg)
            return False
        ndv_single_dict = load_json_from_file(ndv_single_file)

    if isinstance(ndv_mulcol_file, dict):
        ndv_mulcol_dict = ndv_mulcol_file
    else:
        if ndv_mulcol_file and os.path.exists(ndv_mulcol_file):
            ndv_mulcol_dict = load_json_from_file(ndv_mulcol_file)
        else:
            ndv_mulcol_dict = {}

    if isinstance(gt_rec_in_ranges_file, dict):
        gt_rec_in_ranges = gt_rec_in_ranges_file
    else:
        if gt_rec_in_ranges_file and os.path.exists(gt_rec_in_ranges_file):
            gt_rec_in_ranges = load_json_from_file(gt_rec_in_ranges_file)
        else:
            gt_rec_in_ranges = {}

    if isinstance(gt_req_resp_file, dict):
        gt_req_resp = gt_req_resp_file
    else:
        if gt_req_resp_file and os.path.exists(gt_req_resp_file):
            gt_req_resp = load_json_from_file(gt_req_resp_file)
        else:
            gt_req_resp = {}

    db_stat_dict, _ = meta_dict_to_sample_file(
        stats_dict={videx_db: stats_dict},
        hist_dict={videx_db: hist_dict},
        ndv_single_dict={videx_db: ndv_single_dict},
        multi_ndv_dict={videx_db: ndv_mulcol_dict},
        gt_rec_in_ranges={videx_db: gt_rec_in_ranges},
        gt_req_resp={videx_db: gt_req_resp},
        # use_gt=True,
    )

    meta_dict = {videx_db: {}}
    db_config = VariablesAboutIndex()
    for table_name, table_dict in stats_dict.items():
        db_config.myisam_max_sort_file_size.set_value(table_dict['myisam_max_sort_file_size'])
        db_config.innodb_page_size.set_value(table_dict['innodb_page_size'])
        db_config.innodb_buffer_pool_size.set_value(table_dict['innodb_buffer_pool_size'])

        if pd.isna(table_dict['AUTO_INCREMENT']):
            table_dict['AUTO_INCREMENT'] = 0
        meta_dict[videx_db.lower()][table_name.lower()] = Table(
            name=table_dict['TABLE_NAME'],
            db=table_dict['TABLE_SCHEMA'],
            engine=table_dict['ENGINE'],
            row_format=table_dict['ROW_FORMAT'],
            rows=table_dict['TABLE_ROWS'],
            avg_row_length=table_dict['AVG_ROW_LENGTH'],
            data_length=table_dict['DATA_LENGTH'],
            index_length=table_dict['INDEX_LENGTH'],
            data_free=table_dict['DATA_FREE'],
            auto_increment=table_dict['AUTO_INCREMENT'],
            create_time=table_dict['CREATE_TIME'],
            update_time=table_dict['UPDATE_TIME'],
            check_time=table_dict['CHECK_TIME'],
            collation=table_dict['TABLE_COLLATION'],
            charset=table_dict.get('charset'),
            comment=table_dict['TABLE_COMMENT'],
            ddl=table_dict['DDL'],
            table_size=None,
            table_type=table_dict['TABLE_TYPE'],
            create_options=None,
            columns=[Column.from_dict(col_meta_dict) for col_meta_dict in table_dict.get('columns', [])],
            indexes=[Index.from_dict(index_meta_dict) for index_meta_dict in table_dict.get('indexes', [])],
            cluster_index_size=table_dict['CLUSTERED_INDEX_SIZE'],
            other_index_sizes=table_dict['SUM_OF_OTHER_INDEX_SIZES'],
        )

    req_obj = VidexDBTaskStats(task_id=task_id,
                               meta_dict=meta_dict,
                               stats_dict=db_stat_dict,
                               db_config=db_config,
                               )
    return req_obj


class VidexMetaGetter(ABC):
    @abstractmethod
    def get_meta_by_task_id(self, task_id: str) -> VidexDBTaskStats:
        """
        Get task metadata by task ID.

        This is an abstract method that must be implemented by subclasses.

        Args:
            task_id (str): The ID of the task.

        Returns:
            VidexDBTaskStats: The metadata of the task.
        """
        raise NotImplementedError
