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

from sub_platforms.sql_opt.column_statastics.statistics_info import PGTableStatisticsInfo
from sub_platforms.sql_opt.common.pydantic_utils import PydanticDataClassJsonMixin
from sub_platforms.sql_opt.env.rds_env import Env
from sub_platforms.sql_opt.meta import PGTable
from sub_platforms.sql_opt.videx.videx_utils import load_json_from_file, dump_json_to_file, GT_Table_Return, \
    target_env_available_for_videx

class VidexDBTaskStats(BaseModel, PydanticDataClassJsonMixin):
    task_id: Optional[str]
    meta_dict: Dict[str,Dict[str,PGTable]]
    stats_dict: Dict[str,Dict[str,PGTableStatisticsInfo]]

    def model_post_init(self, __context: Any) -> None:
        pass

    def get_table_stats_info(self, db_name: str, table_name: str,schema_name: str = 'public') -> Optional[PGTableStatisticsInfo]:
        pass

    def get_table_meta(self, db_name: str, table_name: str, schema_name: str = 'public') -> Optional[PGTable]:
        pass

    def get_stats_info_keys(self) -> Dict[str, List[str]]:
        pass

    def get_meta_info_keys(self) -> Dict[str, List[str]]:
        pass

    def get_expect_response(self, req_json, result2str: bool = True):
        pass
    
    @property
    def key(self):
        return self.to_key(self.task_id)
    
    def key_is_none(self):
        return not self.task_id or self.task_id == 'None'
    
    @staticmethod
    def to_key(task_id: str) -> str:
        return f"{task_id}"
    
    def merge_with(self, other: 'VidexDBTaskStats', inplace: bool = False) -> Optional['VidexDBTaskStats']:
        pass

def fetch_all_meta_with_one_file_for_pg(meta_path: Union[str, dict],
                                 env: Env, target_db: str, all_table_names: List[str] = None
                                 ) -> Tuple[dict, dict, dict, dict]:
    
    temp_dir = f"temp_meta_{int(time.time())}"
    os.makedirs(temp_dir, exist_ok=True)

    try:
        stats_dict, _, _, _ = fetch_all_meta_for_videx(
            env, target_db, all_table_names,
            result_dir=temp_dir
        )
        if isinstance(meta_path, str):
            metadata = {
                'stats_dict': stats_dict,
            }
            dump_json_to_file(meta_path, metadata)
        return stats_dict, {}, {}, {}
    finally:
        shutil.rmtree(temp_dir)

def fetch_all_meta_for_videx(env: Env, target_db: str, all_table_names: List[str] = None,
                             result_dir: str = None) -> Tuple[dict, dict, dict, dict]:
    stats_file = f'videx_pg_{target_db}_info_stats.json'
    # fetch meta data
    if result_dir is not None and os.path.exists(os.path.join(result_dir, stats_file)):
        return NotImplementedError("Fetching from existing file is not supported in this context.")
    else: 
        stats_dict = fetch_information_schema(env, target_db)

    if all_table_names is None or len(all_table_names) == 0:
        all_table_names = list(stats_dict.keys())
    else:
        stats_dict = {k: v for k, v in stats_dict.items() if k.lower() in set(t.lower() for t in all_table_names)}
    
    #TODO: pg_statistic & pg_statistic_ext

    if result_dir is not None:
       os.makedirs(result_dir, exist_ok=True)
       dump_json_to_file(os.path.join(result_dir, stats_file), stats_dict)

    return stats_dict, {}, {}, {}

def fetch_information_schema(env: Env, target_dbname: str) -> Dict[str, dict]:
    """
    fetch metadata
    Args:
        env:
        target_dbname:

    Returns:
        lower table -> rows (to construct VidexTableStats), 不包含 db 层
    """
    # part 1: basic
    sql = """
        SELECT table_catalog,table_schema,table_name,table_type,
        self_referencing_column_name,reference_generation,user_defined_type_catalog,
        user_defined_type_schema,user_defined_type_name,is_insertable_into,is_typed,
        commit_action FROM information_schema.TABLES WHERE table_catalog = '%s 
        && table_schema NOT IN ('pg_catalog', 'information_schema')
    """ % target_dbname

    basic_list: pd.DataFrame = env.query_for_dataframe(sql).to_dict(orient='records')
    res_dict = {}

    for row in basic_list:
        table_name = row['table_name'].lower()
        res_dict[table_name] = row

        table_obj: PGTable = env.get_table_meta(target_dbname,row["table_name"],row["table_schema"])
        res_dict[table_name]['columns'] = [json.loads(c.to_json()) for c in table_obj.columns]
        res_dict[table_name]['indexes'] = [json.loads(i.to_json()) for i in table_obj.indexes]

    res_dict = {k.lower(): v for k, v in res_dict.items()}
    return res_dict

def construct_videx_task_meta_from_local_files_for_pg(task_id, videx_db,
                                               stats_file: Union[str, dict],
                                               raise_error: bool = False
                                              ) -> VidexDBTaskStats:
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

    meta_dict = {videx_db:{}}
    for table_name,table_dict in stats_dict.items():
        meta_dict[videx_db][table_name] = PGTable(
            #TODO
        )
    req_obj = VidexDBTaskStats(
        task_id=task_id,
        meta_dict=meta_dict,
        stats_dict={}
    )
    return req_obj

def meta_dict_to_sample_file(
        stats_dict,
        hist_dict,
        ndv_single_dict,
        multi_ndv_dict,
        gt_rec_in_ranges,
        gt_req_resp) -> Tuple[Dict[str, Dict[str, PGTableStatisticsInfo]], None]:
    
    """
    TODO: constuct PGTableStatisticsInfo form a list of metadata
    """
    def to_lower_db_tb(d):
        return {k.lower(): {k2.lower(): v2 for k2, v2 in v.items()} for k, v in d.items()}
    stats_dict = to_lower_db_tb(stats_dict)
    numerical_info: Dict[str, Dict[str, PGTableStatisticsInfo]] = defaultdict(dict)
    return numerical_info, None