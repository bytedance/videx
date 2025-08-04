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
        commit_action FROM information_schema.TABLES WHERE table_schema = '%s'
    """ % target_dbname

    basic_list: pd.DataFrame = env.query_for_dataframe(sql).to_dict(orient='records')
    res_dict = {}

    