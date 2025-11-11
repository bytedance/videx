"""
Copyright (c) 2024 Bytedance Ltd. and/or its affiliates
SPDX-License-Identifier: MIT
"""
import logging
from enum import Enum
from typing import List, Dict, Optional, Union
from pydantic import BaseModel, Field

from sub_platforms.sql_opt.common.pydantic_utils import PydanticDataClassJsonMixin
from sub_platforms.sql_opt.databases.mysql.mysql_command import MySQLVersion


class VariableScope(Enum):
    SESSION = "SESSION"
    GLOBAL = "GLOBAL"
    BOTH = "BOTH"


class MysqlVariable(BaseModel, PydanticDataClassJsonMixin):
    """
    Args:
        name: 变量名称
        scope: 作用域，可选项 SESSION | GLOBAL | BOTH
        version: 支持的 VERSION 列表，每一项是 MySQL_57 | MySQL_8
        dynamic: 是否支持在动态变化，无需重启生效（来自官方文档）
        read_only: 是否为只读属性（来自官方文档）
        need_set: 是否需要进行设置（来自索引相关的需求）
        is_update: 是否被更新过 value
    """
    name: str
    scope: VariableScope
    version: List[MySQLVersion]
    dynamic: bool = Field(default=None)
    read_only: bool = Field(default=False)
    need_set: bool = Field(default=True)
    is_update: bool = Field(default=False)

    def set_value(self, val):
        raise NotImplementedError

    def generate_set_statement(self, version: MySQLVersion):
        raise NotImplementedError

    def get_value(self):
        raise NotImplementedError

    def get_value(self, key=None):
        raise NotImplementedError

    def generate_set_statements(self, version: MySQLVersion):
        ret = []
        if self.need_set and self.is_update and version in self.version:
            # N.B. 考虑到 SESSION only 的环境变量不涉及索引推荐，
            # 为避免引入后续设置复杂性，当前不支持 SESSION only 的环境变量设置
            if self.scope == VariableScope.GLOBAL or self.scope == VariableScope.BOTH:
                value = self.get_value()
                if value != "":
                    # N.B. 由于多值属性的特殊性，需要给所有值外侧进行添加引号
                    if isinstance(self, MultiValueVariable):
                        value = f'"{value}"'
                    ret.append(f"global {self.name}={value}")
            else:
                logging.warning(f"not support {self.name} generate set statement")
        return ret


class SingleValueVariable(MysqlVariable):
    value: Optional[Union[str, int]] = Field(default=None)

    def set_value(self, val):
        if val is None or val == "":
            return
        self.is_update = True
        self.value = val

    def get_value(self):
        if not self.is_update:
            logging.warning(f"{self.name} not updated, return empty str")
            return ""
        return self.value


class MultiValueVariable(MysqlVariable):
    fields: Dict[str, str] = Field(default_factory=dict)

    def set_value(self, val):
        if val is None or val == "":
            return
        self.is_update = True
        for item in val.split(","):
            k, v = item.split("=")
            self.fields[k] = v

    def get_value(self, key: str = None):
        """获取多值属性的值。
        指定 key 时，返回相应 field 的值，
        否则返回整个多值属性的值。
        """
        if not self.is_update:
            logging.warning(f"{self.name} not updated, return empty str")
            return ""

        if key is None:
            return ",".join([f"{k}={v}" for k, v in self.fields.items()])
        return self.fields.get(key, "")


DEFAULT_INNODB_PAGE_SIZE = 16384


class VariablesAboutIndex(BaseModel, PydanticDataClassJsonMixin):
    optimizer_switch: MultiValueVariable = Field(default_factory=lambda: MultiValueVariable(name="optimizer_switch",
                                                                                            scope=VariableScope.BOTH,
                                                                                            version=[MySQLVersion.MySQL_57,
                                                                                                     MySQLVersion.MySQL_8,
                                                                                                     MySQLVersion.MariaDB_11_8],
                                                                                            dynamic=True,
                                                                                            read_only=False,
                                                                                            need_set=True))
    sort_buffer_size: SingleValueVariable = Field(default_factory=lambda: SingleValueVariable(name="sort_buffer_size",
                                                                                              scope=VariableScope.BOTH,
                                                                                              version=[MySQLVersion.MySQL_57,
                                                                                                       MySQLVersion.MySQL_8,
                                                                                                       MySQLVersion.MariaDB_11_8],
                                                                                              dynamic=True,
                                                                                              read_only=False,
                                                                                              need_set=False))
    join_buffer_size: SingleValueVariable = Field(default_factory=lambda: SingleValueVariable(name="join_buffer_size",
                                                                                              scope=VariableScope.BOTH,
                                                                                              version=[MySQLVersion.MySQL_57,
                                                                                                       MySQLVersion.MySQL_8,
                                                                                                       MySQLVersion.MariaDB_11_8],
                                                                                              dynamic=True,
                                                                                              read_only=False,
                                                                                              need_set=True))
    tmp_table_size: SingleValueVariable = Field(default_factory=lambda: SingleValueVariable(name="tmp_table_size",
                                                                                            scope=VariableScope.BOTH,
                                                                                            version=[MySQLVersion.MySQL_57,
                                                                                                     MySQLVersion.MySQL_8,
                                                                                                     MySQLVersion.MariaDB_11_8],
                                                                                            dynamic=True,
                                                                                            read_only=False,
                                                                                            need_set=True))
    max_heap_table_size: SingleValueVariable = Field(default_factory=lambda: SingleValueVariable(name="max_heap_table_size",
                                                                                                 scope=VariableScope.BOTH,
                                                                                                 version=[
                                                                                                     MySQLVersion.MySQL_57,
                                                                                                     MySQLVersion.MySQL_8,
                                                                                                     MySQLVersion.MariaDB_11_8],
                                                                                                 dynamic=True,
                                                                                                 read_only=False,
                                                                                                 need_set=True))
    innodb_large_prefix: SingleValueVariable = Field(default_factory=lambda: SingleValueVariable(name="innodb_large_prefix",
                                                                                                 scope=VariableScope.GLOBAL,
                                                                                                 version=[
                                                                                                     MySQLVersion.MySQL_57],
                                                                                                 dynamic=True,
                                                                                                 read_only=False,
                                                                                                 need_set=True))
    max_seeks_for_key: SingleValueVariable = Field(default_factory=lambda: SingleValueVariable(name="max_seeks_for_key",
                                                                                               scope=VariableScope.BOTH,
                                                                                               version=[MySQLVersion.MySQL_57,
                                                                                                        MySQLVersion.MySQL_8,
                                                                                                        MySQLVersion.MariaDB_11_8],
                                                                                               dynamic=True,
                                                                                               read_only=False,
                                                                                               need_set=True))
    eq_range_index_dive_limit: SingleValueVariable = Field(default_factory=lambda: SingleValueVariable(name="eq_range_index_dive_limit",
                                                                                                       scope=VariableScope.BOTH,
                                                                                                       version=[MySQLVersion.MySQL_57,
                                                                                                                MySQLVersion.MySQL_8,
                                                                                                                MySQLVersion.MariaDB_11_8],
                                                                                                       dynamic=True,
                                                                                                       read_only=False,
                                                                                                       need_set=True))
    optimizer_prune_level: SingleValueVariable = Field(default_factory=lambda: SingleValueVariable(name="optimizer_prune_level",
                                                                                                   scope=VariableScope.BOTH,
                                                                                                   version=[MySQLVersion.MySQL_57,
                                                                                                            MySQLVersion.MySQL_8,
                                                                                                            MySQLVersion.MariaDB_11_8],
                                                                                                   dynamic=True,
                                                                                                   read_only=False,
                                                                                                   need_set=True))
    optimizer_search_depth: SingleValueVariable = Field(default_factory=lambda: SingleValueVariable(name="optimizer_search_depth",
                                                                                                    scope=VariableScope.BOTH,
                                                                                                    version=[MySQLVersion.MySQL_57,
                                                                                                             MySQLVersion.MySQL_8,
                                                                                                             MySQLVersion.MariaDB_11_8],
                                                                                                    dynamic=True,
                                                                                                    read_only=False,
                                                                                                    need_set=True))
    range_optimizer_max_mem_size: SingleValueVariable = Field(default_factory=lambda: SingleValueVariable(name="range_optimizer_max_mem_size",
                                                                                                          scope=VariableScope.BOTH,
                                                                                                          version=[MySQLVersion.MySQL_57,
                                                                                                                   MySQLVersion.MySQL_8],
                                                                                                          dynamic=True,
                                                                                                          read_only=False,
                                                                                                          need_set=True))
    version: SingleValueVariable = Field(default_factory=lambda: SingleValueVariable(name="version",
                                                                                     scope=VariableScope.BOTH,
                                                                                     version=[MySQLVersion.MySQL_57,
                                                                                              MySQLVersion.MySQL_8,
                                                                                              MySQLVersion.MariaDB_11_8],
                                                                                     dynamic=False,
                                                                                     read_only=True,
                                                                                     need_set=False))

    innodb_page_size: SingleValueVariable = Field(default_factory=lambda: SingleValueVariable(name="innodb_page_size",
                                                                                     scope=VariableScope.GLOBAL,
                                                                                     version=[MySQLVersion.MySQL_57,
                                                                                              MySQLVersion.MySQL_8,
                                                                                              MySQLVersion.MariaDB_11_8],
                                                                                     dynamic=False,
                                                                                     read_only=True,
                                                                                     need_set=False))

    innodb_buffer_pool_size: SingleValueVariable = Field(default_factory=lambda: SingleValueVariable(name="innodb_buffer_pool_size",
                                                                                     scope=VariableScope.GLOBAL,
                                                                                     version=[MySQLVersion.MySQL_57,
                                                                                              MySQLVersion.MySQL_8,
                                                                                              MySQLVersion.MariaDB_11_8],
                                                                                     dynamic=False,
                                                                                     read_only=True,
                                                                                     need_set=False))

    myisam_max_sort_file_size: SingleValueVariable = Field(default_factory=lambda: SingleValueVariable(name="myisam_max_sort_file_size",
                                                                                     scope=VariableScope.GLOBAL,
                                                                                     version=[MySQLVersion.MySQL_57,
                                                                                              MySQLVersion.MySQL_8,
                                                                                              MySQLVersion.MariaDB_11_8],
                                                                                     dynamic=False,
                                                                                     read_only=True,
                                                                                     need_set=False))

    def get_all_attributes(self):
        return iter(self.__dict__.items())
