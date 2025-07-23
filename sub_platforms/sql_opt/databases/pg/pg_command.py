import datetime
import logging
import re
import math
from enum import Enum
from typing import List

import numpy as np
from numpy import datetime64

from sub_platforms.sql_opt.videx.videx_mysql_utils import AbstractMySQLUtils
from sub_platforms.sql_opt.meta import Table, Column, Index, IndexColumn, IndexType
from sub_platforms.sql_opt.databases.pg.explain_result import PGExplainResult, PGExplainItem

class PGVersion(Enum):
    pass

def get_mysql_version(mysql_util: AbstractMySQLUtils):
    return

def datetime64_to_datetime(date_obj):
    if date_obj is None:
        return date_obj
    if isinstance(date_obj, datetime64):
        return datetime.datetime.fromtimestamp(date_obj.tolist() / 1000000000)
    return date_obj

class PGCommand:
    def __init__(self, pg_util: AbstractMySQLUtils, version: PGVersion):
        self.pg_util = pg_util
        self.version = version

    def get_table_columns(self, db_name, table_name) -> List[Column]:
        return
    
    def get_table_indexes(self, db_name, table_name) -> List[Index]:
        return
    
    def get_table_meta(self, db_name, table_name):
        return
    
    def explain(self, sql: str, format: str = None) -> PGExplainResult:
        return
    
    def explain_for_table(self, sql: str) -> List[PGExplainItem]:
        return
    
