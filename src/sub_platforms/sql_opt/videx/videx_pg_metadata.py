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

from sub_platforms.sql_opt.column_statastics.statistics_info_pg import PGTableStatisticsInfo
from sub_platforms.sql_opt.env.rds_env import Env
from sub_platforms.sql_opt.pg_meta import PGTable,PGColumn, PGIndex ,PGStatistic, PGStatisticExt,PGStatisticSlot
from sub_platforms.sql_opt.videx.videx_utils import load_json_from_file, dump_json_to_file, GT_Table_Return, \
    target_env_available_for_videx,pg_serialize_schema_table,pg_deserialize_schema_table
from sub_platforms.sql_opt.videx.videx_metadata import VidexDBTaskStats
from sub_platforms.sql_opt.videx.videx_utils import pg_deserialize_schema_table

def fetch_all_meta_with_one_file_for_pg(meta_path: Union[str, dict],
                                 env: Env, target_db: str, all_table_names: List[str] = None
                                 ) -> Tuple[dict, dict, dict, dict]:
    temp_dir = f"temp_meta_{int(time.time())}"
    os.makedirs(temp_dir, exist_ok=True)

    try:
        stats_dict, statistic_dict, _, _ = fetch_all_meta_for_videx(
            env, target_db, all_table_names,
            result_dir=temp_dir
        )
        if isinstance(meta_path, str):
            metadata = {
                'stats_dict': stats_dict,
                'statistic_dict': statistic_dict
            }
            dump_json_to_file(meta_path, metadata)
        return stats_dict, statistic_dict, {}, {}
    finally:
        shutil.rmtree(temp_dir)

def fetch_all_meta_for_videx(env: Env, target_db: str, all_table_names: List[str] = None,
                             result_dir: str = None) -> Tuple[dict, dict, dict, dict]:
    stats_file = f'videx_pg_{target_db}_info_stats.json'
    statistic_file = f'videx_pg_{target_db}_info_statistics.json'
    statistic_ext_file = f'videx_pg_{target_db}_info_statistics_ext.json'

    # fetch meta data
    if result_dir is not None and os.path.exists(os.path.join(result_dir, stats_file)):
        return NotImplementedError("Fetching from existing file is not supported in this context.")
    else: 
        stats_dict = fetch_information_schema(env, target_db)

    if all_table_names is None or len(all_table_names) == 0:
        all_table_names = list(stats_dict.keys())
    else:
        stats_dict = {k: v for k, v in stats_dict.items() if k.lower() in set(t.lower() for t in all_table_names)}
    
    #TODO: pg_statistic_ext
    if result_dir is not None and os.path.exists(os.path.join(result_dir, statistic_file)): 
       return NotImplementedError("Fetching from existing file is not supported in this context.")
    else:
       statistic_dict = fetch_pg_statistics(env,target_db,all_table_names,True)

    if result_dir is not None:
       os.makedirs(result_dir, exist_ok=True)
       dump_json_to_file(os.path.join(result_dir, stats_file), stats_dict)
       dump_json_to_file(os.path.join(result_dir, statistic_file), statistic_dict)

    return stats_dict, statistic_dict, {}, {}

def fetch_information_schema(env: Env, target_dbname: str) -> Dict[str, dict]:
    """
    fetch metadata
    Args:
        env:
        target_dbname:
    Returns:
        Dict[str, dict]
    """
    # part 1: fetch all table from information_schema.TABLES (view)
    sql = f"""
        SELECT
            table_catalog,
            table_schema,
            table_name,
            table_type,
            self_referencing_column_name,
            reference_generation,
            user_defined_type_catalog,
            user_defined_type_schema,
            user_defined_type_name,
            is_insertable_into,
            is_typed,
            commit_action
        FROM 
            information_schema.TABLES 
        WHERE 
            table_catalog = '{target_dbname}'
            AND table_schema NOT IN ('pg_catalog', 'information_schema')
    """
    basic_list: pd.DataFrame = env.query_for_dataframe(sql).to_dict(orient='records')
    res_dict = {}
    for row in basic_list:
        table_name = row['table_name'].lower()
        schema_name = row['table_schema'].lower()
        schema_table_name = pg_serialize_schema_table(schema_name, table_name)
        res_dict[schema_table_name] = row
        # part 2: fetch table stats from pg_class
        table_obj: PGTable = env.get_table_meta(target_dbname,schema_table_name)
        res_dict[schema_table_name]['reltuples'] = table_obj.reltuples
        res_dict[schema_table_name]['relpages'] = table_obj.relpages
        res_dict[schema_table_name]['relallvisible'] = table_obj.relallvisible
        res_dict[schema_table_name]['columns'] = [json.loads(c.to_json()) for c in table_obj.columns]
        res_dict[schema_table_name]['indexes'] = [json.loads(i.to_json()) for i in table_obj.indexes]
        res_dict[schema_table_name]['ddl'] = table_obj.ddl
    res_dict = {k.lower(): v for k, v in res_dict.items()}
    return res_dict

def fetch_pg_statistics(env: Env, target_dbname: str,all_table_names: List[str],ret_json: bool = False,
                        ) -> Dict[str, Dict[str, Union[PGStatistic, dict]]]:
    res_tables = defaultdict(dict)
    for table_name in all_table_names:
        table_meta: PGTable = env.get_table_meta(target_dbname, table_name)
        for c_id, col in enumerate(table_meta.columns):
            col: PGColumn
            hist = fetch_col_statistic(env, target_dbname, table_meta.table_schema,table_meta.table_name, col.column_name)
            if hist is not None and ret_json:
                hist = hist.to_dict()
            res_tables[str(table_name).lower()][col.column_name] = hist
    return res_tables

def fetch_col_statistic(env, dbname: str, schema: str, table_name: str, col_name: str) -> Optional[PGStatistic]:
    sql = f"""
        SELECT 
            s.*,
            a.attname
        FROM 
            pg_statistic s
        JOIN 
            pg_class c 
        ON 
            s.starelid = c.oid
        JOIN 
            pg_namespace n 
        ON 
            c.relnamespace = n.oid
        JOIN 
            pg_attribute a 
        ON 
            c.oid = a.attrelid 
            AND s.staattnum = a.attnum
        WHERE 
            n.nspname = '{schema}'
            AND c.relname = '{table_name}'
            AND a.attname = '{col_name}';
    """
    res: pd.DataFrame = env.query_for_dataframe(sql)
    print(f'schema: {schema}, relname: {table_name}, col_name: {col_name}, col statistic: {res}\n')
    if len(res) == 0:
        return None

    row = res.iloc[0].to_dict()
    slots: List[PGStatisticSlot] = []
    for i in range(1, 6):
        kind = row.get(f"stakind{i}")
        op = row.get(f"staop{i}")
        coll = row.get(f"stacoll{i}")
        numbers = row.get(f"stanumbers{i}")
        values = row.get(f"stavalues{i}")

        if isinstance(numbers, str):
            numbers = json.loads(numbers.replace("{", "[").replace("}", "]"))
        if isinstance(values, str):
            values = json.loads(values.replace("{", "[").replace("}", "]"))
        # if kind is 0, it means this slot is not used
        if kind != 0:
            slots.append(PGStatisticSlot(
                kind=kind,
                op=op,
                coll=coll,
                numbers=numbers,
                values=values
            ))

    return PGStatistic(
        dbname=dbname,
        table_schema=schema,
        table_name=table_name,
        col_name=col_name,
        stainherit=row["stainherit"],
        stanullfrac=row["stanullfrac"],
        stawidth=row["stawidth"],
        stadistinct=row["stadistinct"],
        slots=slots
    )

def construct_videx_task_meta_from_local_files_for_pg(task_id, videx_db,
                                               stats_file: Union[str, dict],
                                               statistic_file: Union[str, dict],
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

    if isinstance(statistic_file, dict):
        statistic_dict = statistic_file
    else:
        if not os.path.exists(statistic_file):
            err_msg = f"statistic_file not valid: {statistic_file}, return"
            if raise_error:
                raise Exception(err_msg)
            logging.error(err_msg)
            return False
        statistic_dict = load_json_from_file(statistic_file)
    
    db_stat_dict, _ = meta_dict_to_sample_file(
        stats_dict={videx_db: stats_dict},
        statistic_dict={videx_db: statistic_dict}
    )

    meta_dict = {videx_db:{}}
    for table_name,table_dict in stats_dict.items():
        #table_name <- format: [schema.table]
        meta_dict[videx_db.lower()][table_name.lower()] = PGTable(
            dbname = table_dict['table_catalog'],
            table_schema = table_dict['table_schema'],
            table_name = table_dict['table_name'],
            relpages = table_dict['relpages'],
            reltuples = table_dict['reltuples'],
            relallvisible = table_dict['relallvisible'],
            columns=[PGColumn.from_dict(col_meta_dict) for col_meta_dict in table_dict.get('columns', [])],
            indexes=[PGIndex.from_dict(index_meta_dict) for index_meta_dict in table_dict.get('indexes', [])],
            ddl = table_dict['ddl']
        )
    req_obj = VidexDBTaskStats(
        task_id=task_id,
        meta_dict=meta_dict,
        stats_dict= db_stat_dict,
        db_config = {}
    )
    return req_obj

def meta_dict_to_sample_file(
        stats_dict,
        statistic_dict,
    ) -> Tuple[Dict[str, Dict[str, PGTableStatisticsInfo]], None]:
    """
    TODO: constuct PGTableStatisticsInfo form a list of metadata
    """
    def to_lower_db_tb(d):
        return {k.lower(): {k2.lower(): v2 for k2, v2 in v.items()} for k, v in d.items()}
    stats_dict = to_lower_db_tb(stats_dict)
    statistic_dict = to_lower_db_tb(statistic_dict)
    numerical_info: Dict[str, Dict[str, PGTableStatisticsInfo]] = defaultdict(dict)
    for db_name, db_stats_dict in stats_dict.items():
        for table_name, table_raw_stat_dict in db_stats_dict.items():
            s_name,t_name = pg_deserialize_schema_table(table_name)
            table_stat_info = PGTableStatisticsInfo(db_name=db_name, schema_name=s_name,table_name=t_name)
            statistic_data = statistic_dict[db_name][table_name]
            if statistic_data and isinstance(list(statistic_data.values())[0], dict):
                # if histogram_dict is a dict, convert it to HistogramStats object
                statistic_data = {
                    col: PGStatistic.from_dict(hist_data) if hist_data else None
                    for col, hist_data in statistic_data.items()
                }
            table_stat_info.statistic_dict = statistic_data
            numerical_info[db_name.lower()][table_name.lower()] = table_stat_info    
    return numerical_info, None