import datetime
import logging
import re
import math
from enum import Enum
from typing import List

import numpy as np
from numpy import datetime64

from sub_platforms.sql_opt.videx.videx_mysql_utils import AbstractMySQLUtils
from sub_platforms.sql_opt.pg_meta import PGTable, PGColumn, PGIndex, PGIndexColumn, IndexType
from sub_platforms.sql_opt.databases.pg.explain_result import PGExplainResult, PGExplainItem
from sub_platforms.sql_opt.databases.pg.common_operation import mapping_index_columns

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

    def get_table_columns(self, db_name, table_name, schema_name = 'public') -> List[PGColumn]:
        sql = f"""
            select * from information_schema.columns 
            where table_catalog = '{db_name}' and table_name = '{table_name}'
        """
        df = self.pg_util.query_for_dataframe(sql)
        columns = []
        np = df.to_numpy()
        for row in np:
            column = PGColumn()
            column.table_catalog = row[0]
            column.table_schema = row[1]
            column.table_name = row[2]
            column.column_name = row[3]
            column.ordinal_position = row[4]
            column.column_default = row[5]
            column.is_nullable = row[6]
            column.data_type = row[7]
        return columns
    
    def get_table_indexes(self, db_name, table_name,schema_name = 'public') -> List[PGIndex]:
        #we should gurantee that we are in the correct database
        sql = f"""
            SELECT
                c.relname AS index_name,  -- index_name
                i.indexrelid,             -- oid of index
                i.indisunique,            -- wether unique
                i.indisprimary,            -- wether primary key
                a.amname AS index_type  -- index type
            FROM 
                pg_index i
            JOIN 
                pg_class c ON i.indexrelid = c.oid
            JOIN 
                pg_namespace n ON c.relnamespace = n.oid  
            JOIN 
                pg_am a ON c.relam = a.oid
            WHERE 
                i.indrelid = (SELECT oid as tbname FROM pg_class WHERE relname = '{table_name}' AND relkind = 'r'
                AND n.nspname = {schema_name})
        """
        df = self.pg_util.query_for_dataframe(sql)
        if len(df) == 0:
            return []
        indexs = []
        for idx_info in df:
            is_unique = idx_info['indisunique'].values[0] != 'f'
            is_primary = idx_info['indisprimary'].values[0] != 'f'
            if is_unique and is_primary:
                type = IndexType.PRIMARY
            elif is_unique:
                type = IndexType.UNIQUE
            else:
                type = IndexType.NORMAL
            index = PGIndex(
                type = type,
                db_name = db_name,
                table_name = table_name,
                is_unique = is_unique,
                is_visible = True,
            )
            index_type = idx_info['index_type'].values[0]
            index.index_type = index_type

            index.columns = []
            indexrelid = idx_info['indexrelid'].values[0]
            sql = f"""
                SELECT 
                    a.attname as column_name,
                FROM 
                    pg_attribute a
                JOIN
                    pg_class  c ON a.attrelid = c.oid
                JOIN 
                    pg_index i ON a.attnum = ANY(i.indkey)
                WHERE
                    c.relname = {table_name} and a.attnum > 0 and i.indexrelid = {indexrelid}
                ORDER BY 
                    a.attnum;
            """
            cols_df = self.pg_util.query_for_dataframe(sql)
            for idx,row in cols_df.iterrows():
                column = PGIndexColumn(row['column_name'],db_name, table_name,schema_name)
                #TODO: parse expression from tree_expr format to string
                column.expression = None
                column.collation = 'asc'
                index.columns.append(column)
            indexs.append(index)    
        return indexs
    
    def get_table_meta(self, db_name, table_name,schema_name = 'public'):
        sql = f"""
            SELECT relpages,reltuples, relallvisible
            FROM pg_class c
            JOIN pg_namespace n ON c.relnamespace = n.oid
            WHERE c.relname = '{table_name}' AND n.nspname = '{schema_name}'
        """
        df = self.pg_util.query_for_dataframe(sql)
        table = PGTable()
        table.dbname = db_name
        table.schema_name = schema_name
        table.table_name = table_name
        table.relpages = df['relpages'].values[0]
        table.reltuples = df['reltuples'].values[0]
        table.relallvisible = df['relallvisible'].values[0]
        table.columns = self.get_table_columns(db_name, table_name)
        table.indexes = self.get_table_indexes(db_name, table_name)
        mapping_index_columns(table)
        return table
    
    def explain(self, sql: str, format: str = None) -> PGExplainResult:
        return NotImplementedError("This method is not implemented in this context.")
    
    def explain_for_table(self, sql: str) -> List[PGExplainItem]:
        return NotImplementedError("This method is not implemented in this context.")
    
