import logging

import numpy as np
import pandas as pd
from typing import List, Dict


from sub_platforms.sql_opt.meta import Table, mysql_to_pandas_type
from sub_platforms.sql_opt.common.exceptions import UnsupportedException
from sqlglot.dialects.mysql import MySQL
import sqlglot.expressions


def parse_from_expression(expression):
    ast = sqlglot.parse_one(expression, read=MySQL)
    for node in ast.dfs():
        if isinstance(node, sqlglot.expressions.Column):
            return node.name


def mapping_index_columns(table: Table):
    column_dict = {}
    for column in table.columns:
        column_dict[column.name] = column

    for index in table.indexes:
        for index_column in index.columns:
            column_name = index_column.name
            if column_name is None or column_name == "":
               if index_column.expression is not None:
                   # use replace to support "cast(json_extract(`owners`,_utf8mb4\\'$\\') as char(100) array)"
                   column_name = parse_from_expression(index_column.expression.replace("\\'", "\'"))
                   index_column.name = column_name
               else:
                   raise UnsupportedException(f"table [{table.name}] index[{index.name}] column name is empty")
            index_column.column_ref = column_dict[column_name]


def patch_index_invisible(table: Table):
    """根据 ddl 信息更新 index 是否 invisible"""
    import re
    ddl = table.ddl
    reg_pattern = r'ELBISIVNI 00008.*?\(\s+`(.*?)`\s+YEK'
    re_match = re.findall(reg_pattern, ddl[::-1])
    invisible_indexes = list(map(lambda x: x[::-1], re_match))
    if len(invisible_indexes) == 0:
        return

    for index in table.indexes:
        if index.name in invisible_indexes:
            logging.info(f"{index.db}, {index.table} {index.name} is invisible")
            index.is_visible = False


def replace_illegal_value(data, expected_pd_type):
    if expected_pd_type == 'date':
        data = data.replace('0000-00-00', '1970-01-01')
    elif expected_pd_type == 'datetime':
        data = data.replace('0000-00-00 00:00:00', '1970-01-01 00:00:00')
    return data


def correct_df_type_by_mysql_type(df_sample_raw: pd.DataFrame, table_meta: Table) -> pd.DataFrame:
    col_meta_dict = {column.name.lower(): column for column in table_meta.columns}

    for col in df_sample_raw.columns:
        # 从 table_meta.columns 中寻找 column meta，如果不存在，跳过并 log warning
        col_meta = col_meta_dict.get(col.lower())
        exist_pd_type = str(df_sample_raw[col].dtype)
        if col_meta is None:
            logging.warning(f"sample data has column {col} but does not exists in table meta")
            continue
        expected_pd_type = mysql_to_pandas_type(col_meta.column_type)
        if exist_pd_type == expected_pd_type:
            continue

        try:
            df_sample_raw[col] = replace_illegal_value(df_sample_raw[col], col_meta.data_type.lower())
            if col_meta.data_type.lower() in ['datetime', 'timestamp']:
                df_sample_raw[col] = pd.to_datetime(df_sample_raw[col], format='mixed')
            else:
                # 尝试转换列的数据类型
                df_sample_raw[col] = df_sample_raw[col].astype(expected_pd_type)
            # logging.warning(f"for col: {col}, mysql_type={col_meta.column_type}, "
            #                 f"expected pd_type={expected_pd_type}, but found {exist_pd_type}, convert it.")
        except Exception as e:
            logging.warning(f"meet error when astype. to fix it: {e}")
            # 检查当前列的数据类型是否为 float64 或 float32
            if ('int' in expected_pd_type and
                    (df_sample_raw[col].hasnans \
                     or np.inf in df_sample_raw[col].values \
                     or -np.inf in df_sample_raw[col].values)):
                logging.warning(f"col='{col}' contains NaN/inf but want to convert to {expected_pd_type}. "
                                f"convert to Int (nullable int) instead")
                try:
                    df_sample_raw[col] = df_sample_raw[col].astype(
                        expected_pd_type.replace('uint', 'UInt').replace('int', 'Int'))
                except Exception as e2:
                    logging.error(f"meet error after try convert type. remain original type. {e2}")

    return df_sample_raw


def parse_sample_data_to_dataframe(data: List[Dict[str, str]], table_meta: Table) -> pd.DataFrame:
    if data is None:
        return pd.DataFrame({})
    df_dict = {}
    for row in data:
        for col, val in row.items():
            if col not in df_dict:
                df_dict[col] = []

            df_dict[col].append(val)

    ret = pd.DataFrame(df_dict)
    # Create DataFrame with specific dtypes
    # N.T. 这里没有采用预先指定类型的方案 {col.name: pd.Series(dtype=xxx)} 因为这可能效率非常低
    return correct_df_type_by_mysql_type(ret, table_meta)
