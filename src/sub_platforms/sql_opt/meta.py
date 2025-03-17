"""
Copyright (c) 2024 Bytedance Ltd. and/or its affiliates
SPDX-License-Identifier: MIT
"""

import enum
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from dataclasses_json import config
from dataclasses_json import dataclass_json
from datetime import datetime


@dataclass_json
@dataclass
class TableId:
    db_name: str
    table_name: str

    def __hash__(self):
        return f'{self.db_name}.{self.table_name}'.__hash__()

    def __eq__(self, other):
        if not other:
            return False
        return self.db_name.__eq__(other.db_name) and self.table_name.__eq__(other.table_name)

    def __lt__(self, other):
        if self.db_name < other.db_name:
            return True
        elif self.db_name == other.db_name and self.table_name < other.table_name:
            return True
        else:
            return False


@dataclass_json
@dataclass
class Column:
    name: str = None
    table: str = None
    db: Optional[str] = None
    ordinal_position: int = None
    is_nullable: Optional[str] = None
    data_type: Optional[str] = None
    character_maximum_length: Optional[int] = None
    character_octet_length: Optional[int] = None
    numeric_precision: Optional[int] = None
    numeric_scale: Optional[int] = None
    datetime_precision: Optional[int] = None
    character_set_name: Optional[str] = None
    collation_name: Optional[str] = None
    column_type: Optional[str] = None
    column_key: Optional[str] = None
    # now only used in rds api
    default: Optional[str] = None
    unsigned: Optional[bool] = None
    is_pk: Optional[bool] = None
    is_sharding_key: Optional[bool] = None
    auto_increment: Optional[bool] = False
    invisible: Optional[bool] = False
    # when parsed sql
    alias: Optional[str] = None
    enum_candidates: Optional[List[str]] = None

    def __eq__(self, other):
        """
        判断Column是否相等，以db、table、name均相等作为判断依据
        """
        return self.db == other.db and self.table == other.table and self.name == other.name

    @property
    def enum_values(self):
        if self.enum_candidates is not None and len(self.enum_candidates) > 0:
            return self.enum_candidates
        if self.data_type == 'enum':
            self.enum_candidates = self.column_type.split('(')[1].split(')')[0].split(',')
        return self.enum_candidates

    def __str__(self):
        return f"{self.db}.{self.table}.{self.name}"


@dataclass_json
@dataclass
class OrderColumn(Column):
    asc: bool = True

    @classmethod
    def build_from_column(cls, column: Column, asc: bool):
        if column is None:
            return None
        _column = cls(**column.__dict__)
        _column.asc = asc
        return _column


class IndexType(Enum):
    PRIMARY = 'PRIMARY'
    UNIQUE = 'UNIQUE'
    NORMAL = 'NORMAL'
    FOREIGN_KEY = 'FOREIGN_KEY'


@dataclass_json
@dataclass
class IndexColumn:
    """
        索引中的column，和Column区分开，是因为：
        1. 从索引中不方便补全更多列的信息，后面需要再关联
        2. cardinality是索引中组合前缀的值，在不同索引中会不同
    """
    name: str = None
    cardinality: Optional[int] = None
    sub_part: Optional[int] = 0
    expression: Optional[str] = None
    collation: Optional[str] = 'asc'
    column_ref: Optional[Column] = field(default=None, metadata=config(exclude=lambda x: True))
    table_id: Optional[TableId] = field(default=None)

    @classmethod
    def from_column(cls, column: Column, collation: str = 'asc', sub_part: int = 0, expression: str = None):
        if column is None:
            return None
        index_column = IndexColumn(column.name)
        index_column.column_ref = column
        index_column.table_id = TableId(db_name=column.db, table_name=column.table)
        # TODO temp fix, 临时把大字段设置为255
        if sub_part == 0 and column.data_type.upper() in ['TEXT', 'LONGTEXT']:
            index_column.sub_part = 255
        else:
            index_column.sub_part = sub_part
        index_column.expression = expression
        index_column.collation = collation
        return index_column

    @classmethod
    def simple_column(cls, column_name: str, db_name:str, table_name:str,  collation: str = 'asc', sub_part: int = 0, expression: str = None):
        column = Column(name=column_name, table=table_name, db=db_name, data_type='varchar')
        return cls.from_column(column, collation, sub_part, expression)

    @property
    def db_name(self):
        if self.table_id is not None:
            return self.table_id.db_name
        if self.column_ref is not None:
            return self.column_ref.db
        return None

    @property
    def table_name(self):
        if self.table_id is not None:
            return self.table_id.table_name
        if self.column_ref is not None:
            return self.column_ref.table
        return None

    def __eq__(self, other):
        """
        判断Column是否相等，以db、table、name均相等作为判断依据
        """
        return self.db_name == other.db_name and self.table_name == other.table_name \
               and self.name == other.name and self.expression == other.expression \
               and self.sub_part == other.sub_part and self.collation == other.collation


@dataclass_json
@dataclass
class IndexBasicInfo:
    db_name: Optional[str] = field(default=None)
    table_name: Optional[str] = field(default=None)
    columns: Optional[List[IndexColumn]] = field(default_factory=list)

    def get_column_names(self):
        return [column.name for column in self.columns]


@dataclass_json
@dataclass
class Index(IndexBasicInfo):
    type: Optional[IndexType] = field(default=None)
    name: Optional[str] = field(default=None)
    is_unique: Optional[bool] = field(default=False)
    is_visible: Optional[bool] = True
    index_type: Optional[str] = None

    @property
    def db(self):
        return self.db_name

    @property
    def table(self):
        return self.table_name




    # def to_json(self) -> str:
    #     data_dict = self.__dict__.copy()
    #     data_dict['columns'] = [column.to_json for column in self.columns]
    #     return json.dumps(data_dict)


@dataclass_json
@dataclass
class Table:
    name: str = None
    db: str = None
    engine: Optional[str] = None
    row_format: Optional[str] = None
    rows: Optional[int] = None
    avg_row_length: Optional[int] = None
    # for innodb, data_length is the bytes for clustered index
    data_length: Optional[int] = None
    # for innodb, data_length is the bytes for non-clustered index
    index_length: Optional[int] = None
    data_free: Optional[int] = None
    auto_increment: Optional[int] = None
    create_time: Optional[int] = None
    update_time: Optional[int] = None
    check_time: Optional[int] = None
    collation: Optional[str] = None
    charset: Optional[str] = None
    comment: Optional[str] = None
    ddl: Optional[str] = None
    table_size: Optional[int] = None
    table_type: Optional[str] = None
    create_options: Optional[str] = None
    columns: Optional[List[Column]] = field(default_factory=list)
    indexes: Optional[List[Index]] = field(default_factory=list)
    cluster_index_size: Optional[int] = None
    other_index_sizes: Optional[int] = None

    def __post_init__(self):
        # fill index meta info (db_name, table_name)
        if self.indexes is None:
            return
        for index in self.indexes:
            if index.db_name is None:
                index.db_name = self.db
            if index.table_name is None:
                index.table_name = self.name

    @property
    def table_id(self):
        return TableId(self.db, self.name)

    def support_optimize(self):
        """返回当前 Table 是否支持进行优化及其原因"""
        if str(self.engine).lower() != "innodb":
            return False, f"table engine is {self.engine}"

        if self.indexes is None:
            return False, f"table {self.name} has no pk"

        pk = next((index for index in self.indexes if index.type == IndexType.PRIMARY), None)
        if pk is None or False:
            return False, f"table {self.name} has no pk"

        return True, ""


class OpTypeName(Enum):
    """Format: OP_TYPE_NAME = op_types, op_names"""
    EQ_FUNC = ("EQ_FUNC", "EQUAL_FUNC"), ()
    RANGE_FUNC = ("GT_FUNC", "GE_FUNC", "LT_FUNC", "LE_FUNC", "NE_FUNC"), ()
    BETWEEN_FUNC = ("BETWEEN",), ()
    LIKE_FUNC = ("LIKE_FUNC",), ("like", "regexp", "regexp_like")
    IN_FUNC = ("IN_FUNC",), ("<in_optimizer>", )
    IS_FUNC = ("ISNULL_FUNC", "ISNOTNULL_FUNC"), ()
    MULT_EQUAL_FUNC = ("MULT_EQUAL_FUNC",), ()
    CONSTANT_FUNC = ("TRUE_FUNC", "FALSE_FUNC"), ()

    JSON_FUNC = ("MEMBER_OF_FUNC", "JSON_CONTAINS", "JSON_OVERLAPS"), ()

    @property
    def func_type(self):
        return self.value[0]

    @property
    def func_name(self):
        return self.value[1]

    @classmethod
    def build_from_name(cls, name: str):
        return cls.__members__.get(name)


@dataclass_json
@dataclass
class JoinItem:
    operation: str = None
    op_type: OpTypeName = None
    left: Column = None
    right: Column = None

    def __str__(self):
        return f"{self.left} {self.operation} {self.right}"


# json multi array 是一种更为复杂的函数索引，未来可以自然地拓展到支持函数索引
@dataclass_json
@dataclass
class JsonMultiValueItem:
    # 例如 custinfo->'$.zipcode'
    column_func_str: str = None
    # (empty), SIGNED, UNSIGNED, CHAR(N)
    array_type: str = None
    column: Column = None

    @property
    def index_expression(self) -> str:
        """
        创建索引时，应该填入什么字段。
        ALTER TABLE customers ADD INDEX idx_age_zips(age, (CAST(custinfo->'$.zipcode' AS UNSIGNED ARRAY)) );
        如上，则填入 (CAST(custinfo->'$.zipcode' AS UNSIGNED ARRAY))
        """
        return f"(CAST({self.column_func_str} AS {self.array_type} ARRAY))"


def get_table_uk(table_meta: Table) -> List[List[str]]:
    """
    传入table meta，返回该表所有的UK
    例如：
    [
        ['a', 'b'],
        ['c']
    ]
    """
    uks = []
    for existing_index in table_meta.indexes:
        if existing_index.type.name == 'UNIQUE':
            uk_cols = []
            for i in range(len(existing_index.columns)):
                uk_cols.append(existing_index.columns[i].name) # multiple columns UK
            uks.append(uk_cols)
    return uks


def mysql_to_pandas_type(mysql_type: str):
    """
    将 MySQL datatype 转化为 pandas type
    """
    mysql_type = mysql_type.lower()
    if 'bigint' in mysql_type and 'unsigned' in mysql_type:
        return 'uint64'
    elif 'bigint' in mysql_type:
        return 'int64'
    elif 'int' in mysql_type and 'unsigned' in mysql_type:
        return 'uint32'
    elif 'int' in mysql_type:
        return 'int32'
    elif 'varchar' in mysql_type or 'text' in mysql_type:
        return 'object'  # object in pandas is used for strings
    elif 'double' in mysql_type:
        return 'float64'
    elif 'float' in mysql_type:
        return 'float32'
    elif 'date' in mysql_type or 'datetime' in mysql_type:
        return 'datetime64[ns]'  # 指定具体的时间精度为纳秒
    else:
        return 'object'  # Default type if not matched
