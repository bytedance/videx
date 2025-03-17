"""
Copyright (c) 2024 Bytedance Ltd. and/or its affiliates
SPDX-License-Identifier: MIT
"""

from dataclasses import dataclass, field
from typing import List, Set, Dict, Optional
from collections import defaultdict

from sub_platforms.sql_opt.meta import Column, TableId




@dataclass
class SampleColumnInfo:
    table_id: TableId
    column_name: str
    data_type: Optional[str] = None
    # 大字段，进行前缀采样的长度，0 表示不进行前缀采样
    sample_length: Optional[int] = 0

    @property
    def db_name(self):
        return self.table_id.db_name

    @property
    def table_name(self):
        return self.table_id.table_name

    @classmethod
    def from_column(cls, column: Column, sample_length: int = 0):
        table_id = TableId(column.db, column.table)
        column_info = SampleColumnInfo(table_id, column.name)
        column_info.data_type = column.data_type
        column_info.sample_length = sample_length
        return column_info

    @classmethod
    def new_ins(cls, db_name, table_name, column_name: str, sample_length: int = 0, data_type: str = None):
        table_id = TableId(db_name, table_name)
        column_info = SampleColumnInfo(table_id, column_name)
        column_info.data_type = data_type
        column_info.sample_length = sample_length
        return column_info

    def __hash__(self):
        return hash((self.table_id, self.column_name))

    def __eq__(self, other):
        if not isinstance(other, SampleColumnInfo):
            return False
        return self.table_id == other.table_id and self.column_name == other.column_name


def sample_info_set_to_name_list(col_set: Set[SampleColumnInfo]):
    return [col.column_name for col in col_set]


# @dataclass
class SampleInfo:
    involved_query: Set[str] = Set
    # {db: {table: [Column]}}
    sample_columns: Dict[str, Dict[str, Set[SampleColumnInfo]]] = field(default_factory=dict)
    # sample_info: Dict[str, Dict[str, List[str]]] = None
    sample_fingerprint = None
    
    # @property
    # def sample_dml(self, block_num=10):
    #     """
    #     for the db that supports selecting all tuples
    #     """
    #     dml_list = []
    #     for db in self.sample_info.keys():
    #         for table in self.sample_info[db].keys():
    #             # projections = ','.join([f'{db}.{item}' for item in self.sample_info[db][table]])
    #             projections = ','.join([f'{item}' for item in self.sample_info[db][table]])
    #             dml = f'SELECT {projections} FROM {table};'
    #             dml_list.append(dml)
    #     return dml_list
    #
    # def get_column_statistics(self):
    #     """
    #     Get the total number of tuples and NDV of the table, for the db that supports selecting all tuples
    #     """
    #     dml_list = []
    #     for db in self.sample_info.keys():
    #         for table in self.sample_info[db].keys():
    #             projection_count = ','.join([f'COUNT({item})' for item in self.sample_info[db][table]])
    #             projection_distinct = ','.join([f'COUNT(DISTINCT {item})' for item in self.sample_info[db][table]])
    #             dml = f'SELECT {projection_count}, {projection_distinct} FROM {table};'
    #             dml_list.append(dml)
    #     return dml_list
    #
    # def sample_column_names(self):
    #     cols = []
    #     for db in self.sample_info.keys():
    #         for table in self.sample_info[db].keys():
    #             cols = self.sample_info[db][table]
    #     return cols
    

@dataclass
class SampleResult:
    sample_fingerprint: str = None
    result: tuple = None
    DML: str = None
    numerical_info = {}
