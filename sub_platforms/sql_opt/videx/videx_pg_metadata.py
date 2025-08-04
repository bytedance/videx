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

from sub_platforms.sql_opt.env.rds_env import Env
from sub_platforms.sql_opt.meta import PGTable

def fetch_all_meta_with_one_file(meta_path: Union[str, dict],
                                 env: Env, target_db: str, all_table_names: List[str] = None,
                                 n_buckets=64,
                                 hist_force: bool = False,
                                 drop_hist_after_fetch: bool = True,
                                 hist_mem_size: int = None,
                                 histogram_data: dict = None,
                                 ) -> Tuple[dict, dict, dict, dict]:
    return

def fetch_all_meta_for_videx(env: Env, target_db: str, all_table_names: List[str] = None,
                             result_dir: str = None,
                             n_buckets=64,
                             hist_force: bool = False,
                             drop_hist_after_fetch: bool = True,
                             hist_mem_size: int = None,
                             histogram_data: dict = None,
                             ) -> Tuple[dict, dict, dict, dict]:
    stats_file = f'videx_pg_{target_db}_info_stats.json'

    if result_dir is not None and os.path.exists(os.path.join(result_dir, stats_file)):
        return NotImplementedError("Fetching from existing file is not supported in this context.")
    else: 
        stats_dict = fetch_information_schema(env, target_db)

    if all_table_names is None or len(all_table_names) == 0:
        all_table_names = list(stats_dict.keys())
    else:
        return NotImplementedError("Fetching with specific table names is not supported in this context.")
    
    if result_dir is not None:
        return NotImplementedError("Saving results to a directory is not supported in this context.")
    
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

        table_obj: Table = env.get_table_meta(target_dbname,row["TABEL_NAME"])
        res_dict[table_name]['columns'] = [json.loads(c.to_json()) for c in table_obj.columns]
        res_dict[table_name]['indexes'] = [json.loads(i.to_json()) for i in table_obj.indexes]

    res_dict = {k.lower(): v for k, v in res_dict.items()}
    return res_dict
    