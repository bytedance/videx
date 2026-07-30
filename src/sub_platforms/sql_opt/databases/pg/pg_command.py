import datetime
from enum import Enum
from typing import List

import numpy as np
import pandas as pd

from sub_platforms.sql_opt.videx.videx_mysql_utils import AbstractMySQLUtils
from sub_platforms.sql_opt.pg_meta import PGTable, PGColumn, PGIndex, PGIndexColumn, IndexType
from sub_platforms.sql_opt.databases.pg.explain_result import PGExplainResult, PGExplainItem
from sub_platforms.sql_opt.databases.pg.common_operation import mapping_index_columns
class PGVersion(Enum):
    PG_17 = 'pg_17'
    PG_ELSE = 'pg_else'

def get_pg_version(pg_util: AbstractMySQLUtils):
    sql = "SHOW server_version;"
    df = pg_util.query_for_dataframe(sql)
    version_str = df['server_version'].values[0]
    return PGVersion.PG_17 if version_str.startswith('17') else PGVersion.PG_ELSE

def datetime64_to_datetime(date_obj):
    if date_obj is None:
        return date_obj
    if isinstance(date_obj, np.datetime64):
        return datetime.datetime.fromtimestamp(date_obj.tolist() / 1000000000)
    return date_obj

class PGCommand:
    def __init__(self, pg_util: AbstractMySQLUtils, version: PGVersion):
        self.pg_util = pg_util
        self.version = version

    def get_table_columns(self, db_name, table_name, schema_name = 'public') -> List[PGColumn]:
        sql = f"""
            SELECT
                *
            FROM
                information_schema.columns
            WHERE
                table_catalog = '{db_name}' 
                AND table_name = '{table_name}'
        """
        df = self.pg_util.query_for_dataframe(sql)
        columns = []
        np = df.to_numpy()
        for row in np:
            column = PGColumn(
                table_catalog = row[0],
                table_schema = row[1],
                table_name = row[2],
                column_name = row[3],
                ordinal_position = row[4],
                column_default = row[5],
                is_nullable = row[6],
                data_type = row[7]
            )
            columns.append(column)
        return columns
    
    def get_table_indexes(self, db_name, table_name, schema_name='public') -> List[PGIndex]:
        sql = f"""
            SELECT
                c.relname AS index_name,
                i.indexrelid,
                i.indisunique,
                i.indisprimary,
                a.amname AS index_type
            FROM 
                pg_index i
            JOIN 
                pg_class c 
            ON 
                i.indexrelid = c.oid
            JOIN 
                pg_namespace n 
            ON 
                c.relnamespace = n.oid
            JOIN 
                pg_am a 
            ON 
                c.relam = a.oid
            WHERE i.indrelid = (
                SELECT 
                    pc.oid
                FROM 
                    pg_class pc
                JOIN 
                    pg_namespace pn 
                ON 
                    pc.relnamespace = pn.oid
                WHERE pc.relname = '{table_name}'
                  AND pn.nspname = '{schema_name}'
                  AND pc.relkind = 'r'
            )
        """
        df = self.pg_util.query_for_dataframe(sql)
        if len(df) == 0:
            return []

        indexes: List[PGIndex] = []
        for _, idx_info in df.iterrows():
            is_unique = idx_info['indisunique'] not in ('f', False, 0)
            is_primary = idx_info['indisprimary'] not in ('f', False, 0)

            if is_primary:
                type_ = IndexType.PRIMARY
            elif is_unique:
                type_ = IndexType.UNIQUE
            else:
                type_ = IndexType.NORMAL

            index = PGIndex(
                type=type_,
                db_name=db_name,
                table_name=table_name,
                is_unique=is_unique,
                is_visible=True,
            )
            index.index_type = idx_info['index_type']

            index.columns = []
            indexrelid = idx_info['indexrelid']

            cols_sql = f"""
                SELECT
                    a.attname AS column_name,
                    pg_get_expr(i.indexprs, i.indexrelid) AS expr,
                    pg_get_indexdef(i.indexrelid) AS indexdef
                FROM 
                    pg_index i
                JOIN 
                    pg_class ic 
                ON 
                    i.indexrelid = ic.oid
                LEFT JOIN 
                    pg_attribute a 
                ON 
                    a.attrelid = i.indrelid
                                        AND a.attnum = ANY(i.indkey)
                WHERE 
                    i.indexrelid = {indexrelid}
                ORDER BY 
                    a.attnum NULLS LAST;
            """
            cols_df = self.pg_util.query_for_dataframe(cols_sql)
            for _, row in cols_df.iterrows():
                colname = row.get('column_name')
                expr = row.get('expr')
                column = PGIndexColumn(
                    column_name=colname if pd.notna(colname) else None,
                    db_name=db_name,
                    table_name=table_name,
                    schema_name=schema_name
                )
                column.expression = expr if pd.notna(expr) and expr != '' else None
                column.collation = 'asc'
                index.columns.append(column)
            indexes.append(index)
        return indexes
    
    def get_table_meta(self, db_name, schema_table_name):
        from sub_platforms.sql_opt.videx.videx_utils import pg_deserialize_schema_table
        schema_name,table_name = pg_deserialize_schema_table(schema_table_name)
        # get table ddl
        dump_text = self.pg_util.pg_dump(db_name,schema_name,table_name)
        sql = f"""
            SELECT 
                c.oid, relpages, reltuples, relallvisible
            FROM 
                pg_class c
            JOIN 
                pg_namespace n 
            ON 
                c.relnamespace = n.oid
            WHERE 
                c.relname = '{table_name}' 
                AND n.nspname = '{schema_name}'
        """
        df = self.pg_util.query_for_dataframe(sql)
        table = PGTable(
            dbname = db_name,
            table_schema = schema_name,
            table_name = schema_table_name,
            oid = df['oid'].values[0],
            relpages = df['relpages'].values[0],
            reltuples = df['reltuples'].values[0],
            relallvisible = df['relallvisible'].values[0],
            ddl = dump_text,
            columns = self.get_table_columns(db_name, table_name,schema_name),
            indexes = self.get_table_indexes(db_name, table_name,schema_name)
        )
        mapping_index_columns(table)
        return table
    
    def explain(self, sql: str, format: str = None) -> PGExplainResult:
        raise NotImplementedError("This method is not implemented in this context.")
    
    def explain_for_table(self, sql: str) -> List[PGExplainItem]:
        raise NotImplementedError("This method is not implemented in this context.")