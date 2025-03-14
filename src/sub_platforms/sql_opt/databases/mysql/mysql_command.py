"""
Copyright (c) 2024 Bytedance Ltd. and/or its affiliates
SPDX-License-Identifier: MIT

@ author: bytebrain
@ date: 2025-03-13

"""

import datetime
import logging
import re
import math
from enum import Enum
from typing import List

import numpy as np
from numpy import datetime64

from sub_platforms.sql_opt.videx.videx_mysql_utils import AbstractMySQLUtils
from sub_platforms.sql_opt.common.exceptions import TableNotFoundException, UnsupportedException
from sub_platforms.sql_opt.meta import Table, Column, Index, IndexColumn, IndexType
from sub_platforms.sql_opt.databases.mysql.common_operation import mapping_index_columns
from sub_platforms.sql_opt.databases.mysql.explain_result import MySQLExplainResult, MySQLExplainItem
from sub_platforms.sql_opt.sql_opt_utils.sqlbrain_constants import UNSUPPORTED_MYSQL_DATATYPE


class MySQLVersion(Enum):
    MySQL_57 = 'mysql5.7'
    MySQL_8 = 'mysql8.0'

    @staticmethod
    def get_version_enum(version: str):
        if version is None:
            version = ""
        return MySQLVersion.MySQL_8 if (version.startswith("8") or version == MySQLVersion.MySQL_8.value) else MySQLVersion.MySQL_57

    def __str__(self):
        return self.value


def get_mysql_version(mysql_util: AbstractMySQLUtils):
    sql = "show variables like 'version';"
    df = mysql_util.query_for_dataframe(sql)
    if len(df) == 0:
        return MySQLVersion.MySQL_57
    version_str = df['Value'].values[0]
    if version_str.startswith('8.0'):
        return MySQLVersion.MySQL_8
    return MySQLVersion.MySQL_57


def datetime64_to_datetime(date_obj):
    if date_obj is None:
        return date_obj
    if isinstance(date_obj, datetime64):
        return datetime.datetime.fromtimestamp(date_obj.tolist() / 1000000000)
    return date_obj


class MySQLCommand:
    def __init__(self, mysql_util: AbstractMySQLUtils, version: MySQLVersion):
        self.mysql_util = mysql_util
        self.version = version

    def get_table_columns(self, db_name, table_name) -> List[Column]:
        sql = f"""
            select table_schema, table_name, column_name, ordinal_position, is_nullable,
                data_type, character_maximum_length, character_octet_length, numeric_precision,
                numeric_scale, datetime_precision, character_set_name, collation_name,
                column_type, column_key, extra 
            from information_schema.columns 
            where table_schema='{db_name}' and table_name='{table_name}'
        """
        df = self.mysql_util.query_for_dataframe(sql)
        columns = []
        np = df.to_numpy()
        for row in np:
            column = Column()
            column.db = row[0]
            column.table = row[1]
            column.name = row[2]
            column.ordinal_position = row[3]
            column.is_nullable = row[4]
            column.data_type = row[5]
            data_type = column.data_type
            if data_type is None or data_type.upper() in UNSUPPORTED_MYSQL_DATATYPE:
                raise UnsupportedException(f"{db_name}.{table_name} has an unsupported datatype {data_type}")
            column.character_maximum_length = int(row[6]) if row[6] is not None and not math.isnan(row[6]) else None
            column.character_octet_length = int(row[7]) if row[7] is not None and not math.isnan(row[7]) else None
            column.numeric_precision = int(row[8]) if row[8] is not None and not math.isnan(row[8]) else None
            column.numeric_scale = int(row[9]) if row[9] is not None and not math.isnan(row[9]) else None
            column.datetime_precision = int(row[10]) if row[10] is not None and not math.isnan(row[10]) else None
            column.character_set_name = row[11]
            column.collation_name = row[12]
            column.column_type = row[13]
            column.column_key = row[14]
            column.auto_increment = 'auto_increment' in str(row[15])
            columns.append(column)

        return columns

    def get_table_indexes(self, db_name, table_name) -> List[Index]:
        if self.version == MySQLVersion.MySQL_8:
            sql = f"""
                select table_schema as dbname, table_name as table_name, index_name as index_name, 
                            non_unique as non_unique, seq_in_index as seq_in_index,
                            column_name as column_name, cardinality as cardinality,
                            sub_part as sub_part, is_visible as is_visible,
                            expression as expression, collation as collation, index_type as index_type
                from information_schema.statistics
                where table_schema = '{db_name}' and table_name='{table_name}'
            """
        else:
            sql = f"""
                        select table_schema as dbname, table_name as table_name, index_name as index_name, 
                            non_unique as non_unique, seq_in_index as seq_in_index,
                            column_name as column_name, cardinality as cardinality, 
                            sub_part as sub_part, 'YES' as is_visible, 
                            'NULL' as expression, collation as collation, index_type as index_type
                        from information_schema.statistics
                        where table_schema = '{db_name}' and table_name='{table_name}'
                    """
        df = self.mysql_util.query_for_dataframe(sql)
        if len(df) == 0:
            return []
        df['sub_part'] = df['sub_part'].replace({np.nan: 0}).astype('int')
        df['collation'] = df['collation'].replace({'A': 'asc', 'D': 'desc'})
        group_keys = ['dbname', 'table_name', 'index_name']
        group_df = df.groupby(by=group_keys, dropna=False)
        indexes = []
        for index_info, column_info in group_df:
            non_unique = column_info['non_unique'].values[0]
            # 'table_name', 'index_name', 'seq_in_index', 'column_name',
            # , 'non_unique', 'is_visible', 'expression'
            if non_unique == 0:
                is_unique = True
                if index_info[2] == 'PRIMARY':
                    type = IndexType.PRIMARY
                else:
                    type = IndexType.UNIQUE
            else:
                is_unique = False
                type = IndexType.NORMAL

            is_visible = column_info['is_visible'].values[0] == 'YES'
            index_type = column_info['index_type'].values[0]

            index = Index(type=type, db_name=index_info[0], table_name=index_info[1], name=index_info[2], is_unique=is_unique,
                          is_visible=is_visible)
            index.index_type = index_type

            index.columns = []
            sorted_columns = column_info.sort_values(by=['seq_in_index'])
            for idx, row in sorted_columns.iterrows():
                column = IndexColumn.simple_column(row['column_name'], db_name, table_name)
                column.cardinality = row['cardinality']
                column.sub_part = row['sub_part']
                column.expression = row['expression']
                column.collation = row['collation']
                index.columns.append(column)

            indexes.append(index)

        return indexes

    def get_table_meta(self, db_name, table_name):
        # Note: 无需处理 sharding 的情况
        sql = f"show table status in `{db_name}` like '{table_name}'"
        df = self.mysql_util.query_for_dataframe(sql)

        if len(df) == 0:
            raise TableNotFoundException("table not in env", table_name)
        table = Table()
        table.name = table_name
        table.db = db_name
        table.engine = df['Engine'].values[0]
        table.row_format = df['Row_format'].values[0]
        table.collation = df['Collation'].values[0]
        table.comment = df['Comment'].values[0]
        table.rows = int(df['Rows'].values[0])
        table.avg_row_length = int(df['Avg_row_length'][0])
        table.data_length = int(df['Data_length'].values[0])
        table.index_length = int(df['Index_length'].values[0])
        create_time = datetime64_to_datetime(df['Create_time'].values[0])
        table.create_time = int(create_time.timestamp()) if create_time is not None else None
        update_time = datetime64_to_datetime(df['Update_time'].values[0])
        table.update_time = int(update_time.timestamp()) if update_time is not None else None
        check_time = datetime64_to_datetime(df['Check_time'].values[0])
        table.check_time = int(check_time.timestamp()) if check_time is not None else None
        table.columns = self.get_table_columns(db_name, table_name)
        table.indexes = self.get_table_indexes(db_name, table_name)
        mapping_index_columns(table)

        try:
        # get table stats
            table_stats_sql = f"select n_rows, clustered_index_size, sum_of_other_index_sizes from mysql.innodb_table_stats " \
                              f"where database_name='{db_name}' and table_name='{table_name}'"

            df = self.mysql_util.query_for_dataframe(table_stats_sql)
            if df is not None and len(df) == 1:
                table.rows = int(df['n_rows'].values[0])
                table.cluster_index_size = int(df['clustered_index_size'].values[0])
                table.other_index_sizes = int(df['sum_of_other_index_sizes'].values[0])
        except Exception as e:
            logging.warning(f"get table stats failed, {e}")

        df = self.mysql_util.query_for_dataframe(f'show create table `{db_name}`.`{table_name}`')
        # ddl = self.mysql_util.query_for_value(f'show create table {db_name}.{table_name}')
        ddl = df.values[0][1]
        ddl = re.sub(r'\b(AUTO_INCREMENT|auto_increment)=\d+\b', "", ddl)
        table.ddl = ddl
        return table

    def explain(self, sql: str, format: str = None) -> MySQLExplainResult:
        result = MySQLExplainResult()
        result.format = format
        if format is not None and format.upper() == "JSON":
            result.explain_json = self.mysql_util.query_for_value(f'explain format=JSON {sql}')
        else:
            result.explain_items = self.explain_for_table(sql)
        return result

    def explain_for_table(self, sql: str) -> List[MySQLExplainItem]:
        result = []
        explain_df = self.mysql_util.query_for_dataframe(f'explain {sql}')
        for rid, row in explain_df.iterrows():
            item = MySQLExplainItem()
            item.id = row['id']
            item.select_type = row['select_type']
            item.table = row['table']
            item.partitions = row['partitions']
            item.type = row['type']
            item.possible_keys = row['possible_keys']
            item.key = row['key']
            item.key_len = row['key_len']
            item.ref = row['ref']
            item.rows = row['rows']
            item.filtered = row['filtered']
            item.extra = row['Extra']

            result.append(item)
        return result
