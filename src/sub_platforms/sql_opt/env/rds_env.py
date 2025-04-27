"""
Copyright (c) 2024 Bytedance Ltd. and/or its affiliates
SPDX-License-Identifier: MIT
"""

import json
import logging
import re
import os
import traceback
from abc import ABC, abstractmethod
import pandas as pd
from typing import Dict, List, Optional, Set
from pymysql import InternalError

from sub_platforms.sql_opt.common.db_variable import VariablesAboutIndex, MysqlVariable
from sub_platforms.sql_opt.common.exceptions import UnsupportedSamplingException
from sub_platforms.sql_opt.common.sample_info import SampleColumnInfo
from sub_platforms.sql_opt.meta import Table, Column, Index, IndexColumn, IndexType
from sub_platforms.sql_opt.databases.mysql.mysql_command import MySQLCommand, get_mysql_version, MySQLVersion
from sub_platforms.sql_opt.meta import Table, Column, IndexColumn, IndexType
from sub_platforms.sql_opt.videx.videx_mysql_utils import get_mysql_utils, MySQLConnectionConfig, DBTYPE


def add_backquote(name):
    """
    Add backticks to column names to avoid conflicts with MySQL keywords
    """
    return name if name.startswith('`') and name.endswith('`') else f"`{name}`"


def unify_col_with_value(df: pd.DataFrame):
    """
    Convert the first row of the DataFrame into a list in the format [{ColumnName: column_name, Value: column_value}, ]
    """
    assert df is not None and not df.empty, f"Empty DataFrame {df}"
    # Note: Adding str to Value is intended to convert all types to str, ensuring correctness when dumping to a file later
    return [{"ColumnName": key, "Value": str(val)} for key, val in df.iloc[0].to_dict().items()]


def extract_pk_contents(pk_c_v: List[Dict[str, str]], pk_names: List[str]):
    """Extract the value of the primary key in advance for generating PrimaryValue"""

    values = []
    for pk_name in pk_names:
        for item in pk_c_v:
            if item["ColumnName"] == pk_name:
                values.append(item["Value"])

    assert len(values) == len(pk_names), "Not all pk columns exist"
    return values


class Env(ABC):
    def __init__(self, default_db):
        self.default_db = default_db
        # meta_info : {db: {table: Table:class } }
        self.meta_info: Dict[str, Dict[str, Table]] = {}
        self.config_info = {}
        self.mysql_variables: VariablesAboutIndex = VariablesAboutIndex()
        self.mysql_util = None
        self.worker_id = None
        self.mysql_command = None

    def get_default_db(self):
        return self.default_db

    def set_default_db(self, db_name):
        self.default_db = db_name
        self._switch_db(db_name)

    def set_worker_id(self, worker_id):
        self.worker_id = worker_id

    @abstractmethod
    def _switch_db(self, db_name):
        raise NotImplementedError

    def get_table_meta(self, db_name, table_name) -> Table:
        """get table meta, if not exists, fetch it
        Args:
            db_name (str): database name
            table_name (str): table name

        Returns:
            table (Table): table meta info

        """
        if table_name is None or table_name.strip() == '':
            raise Exception('table_name is None in get_table_meta')
        if db_name is None or db_name.strip() == '':
            db_name = self.default_db
        # NOTE: only table name case-insensitive, keep db name in the original case.
        lower_table_name = table_name.lower()
        if db_name not in self.meta_info:
            self.meta_info[db_name] = {}

        if lower_table_name not in self.meta_info[db_name]:
            self.meta_info[db_name][lower_table_name] = self._request_meta_info(db_name, table_name, logic_db=db_name)
        return self.meta_info[db_name][lower_table_name]

    def remove_table_meta(self, db_name, table_name):
        if db_name is None or db_name.strip() == '' or table_name is None or table_name.strip() == '':
            logging.warning("db_name or table_name is empty, no need to remove")
            return
        if db_name in self.meta_info:
            lower_table_name = table_name.lower()
            if lower_table_name in self.meta_info[db_name]:
                del self.meta_info[db_name][lower_table_name]

    def get_column_meta(self, db_name: str, table_name: str, column_name: str) -> Optional[Column]:
        table: Table = self.get_table_meta(db_name, table_name)
        if not table.columns:
            return None
        satisfied_cols = [col for col in table.columns if column_name.lower() == col.name.lower()]
        if not satisfied_cols:
            return None
        return satisfied_cols[0]

    def get_exist_index_count(self, table_name: str, db_name: str = None) -> int:
        """
        get how much existing index
        Args:
            table_name:
            db_name:

        Returns:

        """
        if db_name is None:
            db_name = self.default_db
        return len(self.get_table_meta(db_name, table_name).indexes)

    def simple_str_table_meta(self):
        from collections import defaultdict
        simple_dict = defaultdict(dict)
        for db_name, db_dict in self.meta_info.items():
            for table_name, table in db_dict.items():
                if table is None:
                    logging.warning(f"for print env.table_meta. table: {table_name} is None")
                    continue
                if table.indexes is None:
                    logging.warning(f"for print env.table_meta. table: {table_name} indexes is None")
                    continue
                for idx in table.indexes:
                    if idx is None:
                        logging.warning(f"for print env.table_meta. There is None in {table_name}.indexes[]")
                        continue
                simple_dict[db_name][table_name] = f"Table({table.name}, idx={[idx.name for idx in table.indexes]})"
        return str(simple_dict)

    def get_pk_columns(self, db_name, table_name) -> List[IndexColumn]:
        table = self.get_table_meta(db_name, table_name)
        if table is None:
            return None
        for index in table.indexes:
            if index.type == IndexType.PRIMARY:
                return index.columns
        return None

    @property
    def instance(self):
        return self._get_instance()

    @abstractmethod
    def _get_instance(self):
        return NotImplementedError

    @abstractmethod
    def get_sample_data(self, db_name: str, table_name: str, table_meta: Table, sample_cols: Set[SampleColumnInfo], pk_names: List[str],
                        min_id: List[Dict], max_id: List[Dict], limit: int = 10, random=False,
                        orderby='desc', shard_no: int = 0):
        return NotImplementedError

    @abstractmethod
    def get_pk_id_range(self, db_name: str, table_name: str, part_no: int):
        raise NotImplementedError

    @abstractmethod
    def _request_meta_info(self, db_name, table_name, logic_db) -> Table:
        raise NotImplementedError

    @abstractmethod
    def execute(self, sql, params=None):
        raise NotImplementedError

    @abstractmethod
    def execute_rollback(self, sql, params=None):
        raise NotImplementedError

    @abstractmethod
    def execute_manyquery(self, sql, params=None):
        raise NotImplementedError

    @abstractmethod
    def query_for_dataframe(self, sql, params=None):
        raise NotImplementedError

    @abstractmethod
    def change_index(self, ddl):
        raise NotImplementedError

    @abstractmethod
    def explain(self, sql, format=None):
        raise NotImplementedError

    @abstractmethod
    def get_sqlalchemy_engine(self, dbname: str = None):
        raise NotImplementedError

    @abstractmethod
    def get_variables(self, variables: List[str]):
        raise NotImplementedError

    @abstractmethod
    def reconstruct_connections(self):
        raise NotImplementedError

    def get_version(self) -> MySQLVersion:
        mysql_version = self.mysql_variables.version.get_value()
        if mysql_version is None or mysql_version == '' and self.mysql_command is not None:
            if self.mysql_command.version != '' and self.mysql_command.version is not None:
                return self.mysql_command.version
        version_enum = MySQLVersion.get_version_enum(mysql_version)
        return version_enum


class DirectConnectMySQLEnv(Env, ABC):
    def __init__(self, default_db, mysql_util):
        super(DirectConnectMySQLEnv, self).__init__(default_db=default_db)
        self.mysql_util = mysql_util
        self.mysql_command = MySQLCommand(mysql_util=self.mysql_util, version=get_mysql_version(self.mysql_util))

    def _switch_db(self, db_name):
        self.mysql_util.switch_db(db_name=db_name)

    def _request_meta_info(self, db_name, table_name, logic_db) -> Table:
        return self.mysql_command.get_table_meta(db_name, table_name)

    def get_sample_data(self, db_name: str, table_name: str, table_meta: Table, sample_cols: Set[SampleColumnInfo], pk_names: List[str],
                        min_id: List[Dict], max_id: List[Dict], limit: int = 10, random=False,
                        orderby='desc', shard_no: int = 0):
        """
        sampling data from mysql instance with specified conditions, e.g. min_id, max_id, limit, random, orderby
        """
        # Ensure the SQL remains executable when the column names are keywords.
        pk_names = [add_backquote(pk_name) for pk_name in pk_names]
        projections = []
        for col in sample_cols:
            if col.sample_length > 0:
                projections.append(f'LEFT({add_backquote(col.column_name)}, {col.sample_length}) as {add_backquote(col.column_name)}')
            else:
                projections.append(add_backquote(col.column_name))
        # Ensure the SQL remains executable when the column names are keywords.
        pk_names = [add_backquote(pk_name) for pk_name in pk_names]

        pk_cols = self.get_pk_columns(db_name, table_name)

        def handle_pk_condition(boundary):
            # Ensure the SQL remains executable when the column names are keywords.
            names = [add_backquote(str(b["ColumnName"])) for b in boundary]
            values = [str(b["Value"]) for b in boundary]
            params_placeholders = ["%s"] * len(names)
            return f"({','.join(names)})", f"({','.join(params_placeholders)})", values

        min_names, min_placeholders, min_values = handle_pk_condition(min_id)
        max_names, max_placeholders, max_values = handle_pk_condition(max_id)
        orderby_str = f"{','.join([f'{pk_name} {orderby}' for pk_name in pk_names])}"

        # Note: Use placeholders to avoid syntax errors caused by special characters (", ').
        sql = f"""
            select {",".join(projections)} from `{db_name}`.`{table_name}` 
            where {min_names} >= {min_placeholders} and {max_names} <= {max_placeholders} order by {orderby_str} limit {limit}
        """
        data = self.mysql_util.query_for_dataframe(sql, min_values + max_values)

        return data

    def get_pk_id_range(self, db_name: str, table_name: str, shard_no: str):
        pk_cols = self.get_pk_columns(db_name, table_name)
        pk_names = [f"`{pk_col.column_ref.name}`" for pk_col in pk_cols]

        # request lower bound
        min_query = (f"select {','.join(pk_names)} from `{db_name}`.`{table_name}` order by "
                     f"{','.join([f'{pk_name} asc' for pk_name in pk_names])} limit 1")
        df_min = self.mysql_util.query_for_dataframe(min_query)
        if df_min is None or df_min.empty:
            raise Exception(f'get_pk_id_range lower bound {pk_names} from {db_name}.{table_name} failed')

        # request upper bound
        max_query = (f"select {','.join(pk_names)} from `{db_name}`.`{table_name}` order by "
                     f"{','.join([f'{pk_name} desc' for pk_name in pk_names])} limit 1")
        df_max = self.mysql_util.query_for_dataframe(max_query)
        if df_max is None or df_max.empty:
            raise Exception(f'get_pk_id_range upper bound {pk_names} from {db_name}.{table_name} failed')

        pk_info = {"min_id": unify_col_with_value(df_min),
                   "max_id": unify_col_with_value(df_max)}

        return pk_info

    def execute(self, sql, params=None):
        return self.mysql_util.execute_query(sql, params=params)

    def execute_rollback(self, sql, params=None):
        return self.mysql_util.execute_with_rollback(sql, params=params)

    def execute_manyquery(self, sql, params=None):
        return self.mysql_util.execute_manyquery(sql, params=params)

    def query_for_dataframe(self, sql, params=None):
        return self.mysql_util.query_for_dataframe(sql, params)

    def change_index(self, ddl):
        return self.mysql_util.execute_query(ddl)

    def explain(self, sql, format=None):
        return self.mysql_command.explain(sql, format=format)

    def get_sqlalchemy_engine(self, dbname: str = None):
        return self.mysql_util.get_sqlalchemy_engine(dbname=dbname)

    def get_variables(self, variables: List[str]) -> dict:
        if len(variables) == 0:
            return {}

        query_sql = "show variables where Variable_name in %s;"
        params = (variables,)
        result = self.mysql_util.execute_query(query_sql, params=params)

        variables_data = {key: "" for key in variables}
        if result is None:
            return variables_data
        for key, value in result:
            variables_data[key] = value
        return variables_data

    def reconstruct_connections(self):
        logging.info("reconstruct connection pool for OpenMySQLEnv")
        self.mysql_util.reconstruct_pool()


class OpenMySQLEnv(DirectConnectMySQLEnv):
    def __init__(self, ip, port, usr, pwd, db_name, read_timeout=30, write_timeout=30, connect_timeout=10,
                 max_connections=None,
                 ):
        self.config = MySQLConnectionConfig(
            dbtype=DBTYPE.OPEN_MYSQL,
            host=ip, port=int(port),
            user=usr, pwd=pwd,
            schema=db_name,
            read_timeout=read_timeout,
            write_timeout=write_timeout,
            connect_timeout=connect_timeout,
            max_connections=max_connections,
        )
        self.mysql_util = get_mysql_utils(self.config)
        super(OpenMySQLEnv, self).__init__(default_db=db_name, mysql_util=self.mysql_util)
        self.mysql_command = MySQLCommand(mysql_util=self.mysql_util, version=get_mysql_version(self.mysql_util))

    @staticmethod
    def from_mysql_connection_config(config: MySQLConnectionConfig) -> "OpenMySQLEnv":
        """
        pass into MySQLConnectionConfig，then return OpenMySQLEnv
        Args:
            config:

        Returns:

        """
        assert config.dbtype == DBTYPE.OPEN_MYSQL, f"required DBTYPE.OPEN_MYSQL, given {config.dbtype}"
        return OpenMySQLEnv(
            ip=config.host,
            port=config.port,
            usr=config.user,
            pwd=config.pwd,
            db_name=config.schema,
            read_timeout=config.read_timeout,
            write_timeout=config.write_timeout,
            connect_timeout=config.connect_timeout,
        )

    def __repr__(self):
        return str(self.mysql_util)

    def __str__(self):
        return self.__repr__()

    def _get_instance(self):
        return f'{self.mysql_util.host}:{self.mysql_util.port}'

