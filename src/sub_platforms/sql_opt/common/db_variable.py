"""
Copyright (c) 2024 Bytedance Ltd. and/or its affiliates
SPDX-License-Identifier: MIT

@ author: bytebrain
@ date: 2025-03-13

"""
import logging
from dataclasses import dataclass, field
from dataclasses_json import dataclass_json
from enum import Enum
from typing import List, Dict, Union

from sub_platforms.sql_opt.databases.mysql.mysql_command import MySQLVersion


class VariableScope(Enum):
    SESSION = "SESSION"
    GLOBAL = "GLOBAL"
    BOTH = "BOTH"


@dataclass
class MysqlVariable:
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
    dynamic: bool = field(default=None)
    read_only: bool = field(default=False)
    need_set: bool = field(default=True)
    is_update: bool = field(default=False)

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


@dataclass
class SingleValueVariable(MysqlVariable):
    value: str = field(default=None)

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


@dataclass
class MultiValueVariable(MysqlVariable):
    fields: Dict[str, str] = field(default_factory=dict)

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


@dataclass_json
@dataclass
class VariablesAboutIndex:
    optimizer_switch: MultiValueVariable = field(default_factory=lambda: MultiValueVariable(name="optimizer_switch",
                                                                                            scope=VariableScope.BOTH,
                                                                                            version=[MySQLVersion.MySQL_57,
                                                                                                     MySQLVersion.MySQL_8],
                                                                                            dynamic=True,
                                                                                            read_only=False,
                                                                                            need_set=True))
    sort_buffer_size: SingleValueVariable = field(default_factory=lambda: SingleValueVariable(name="sort_buffer_size",
                                                                                              scope=VariableScope.BOTH,
                                                                                              version=[MySQLVersion.MySQL_57,
                                                                                                       MySQLVersion.MySQL_8],
                                                                                              dynamic=True,
                                                                                              read_only=False,
                                                                                              need_set=False))
    join_buffer_size: SingleValueVariable = field(default_factory=lambda: SingleValueVariable(name="join_buffer_size",
                                                                                              scope=VariableScope.BOTH,
                                                                                              version=[MySQLVersion.MySQL_57,
                                                                                                       MySQLVersion.MySQL_8],
                                                                                              dynamic=True,
                                                                                              read_only=False,
                                                                                              need_set=True))
    tmp_table_size: SingleValueVariable = field(default_factory=lambda: SingleValueVariable(name="tmp_table_size",
                                                                                            scope=VariableScope.BOTH,
                                                                                            version=[MySQLVersion.MySQL_57,
                                                                                                     MySQLVersion.MySQL_8],
                                                                                            dynamic=True,
                                                                                            read_only=False,
                                                                                            need_set=True))
    max_heap_table_size: SingleValueVariable = field(default_factory=lambda: SingleValueVariable(name="max_heap_table_size",
                                                                                                 scope=VariableScope.BOTH,
                                                                                                 version=[
                                                                                                     MySQLVersion.MySQL_57,
                                                                                                     MySQLVersion.MySQL_8],
                                                                                                 dynamic=True,
                                                                                                 read_only=False,
                                                                                                 need_set=True))
    innodb_large_prefix: SingleValueVariable = field(default_factory=lambda: SingleValueVariable(name="innodb_large_prefix",
                                                                                                 scope=VariableScope.GLOBAL,
                                                                                                 version=[
                                                                                                     MySQLVersion.MySQL_57],
                                                                                                 dynamic=True,
                                                                                                 read_only=False,
                                                                                                 need_set=True))
    max_seeks_for_key: SingleValueVariable = field(default_factory=lambda: SingleValueVariable(name="max_seeks_for_key",
                                                                                               scope=VariableScope.BOTH,
                                                                                               version=[MySQLVersion.MySQL_57,
                                                                                                        MySQLVersion.MySQL_8],
                                                                                               dynamic=True,
                                                                                               read_only=False,
                                                                                               need_set=True))
    eq_range_index_dive_limit: SingleValueVariable = field( default_factory=lambda: SingleValueVariable(name="eq_range_index_dive_limit",
                                                                                                        scope=VariableScope.BOTH,
                                                                                                        version=[MySQLVersion.MySQL_57,
                                                                                                                 MySQLVersion.MySQL_8],
                                                                                                        dynamic=True,
                                                                                                        read_only=False,
                                                                                                        need_set=True))
    optimizer_prune_level: SingleValueVariable = field(default_factory=lambda: SingleValueVariable(name="optimizer_prune_level",
                                                                                                   scope=VariableScope.BOTH,
                                                                                                   version=[MySQLVersion.MySQL_57,
                                                                                                            MySQLVersion.MySQL_8],
                                                                                                   dynamic=True,
                                                                                                   read_only=False,
                                                                                                   need_set=True))
    optimizer_search_depth: SingleValueVariable = field(default_factory=lambda: SingleValueVariable(name="optimizer_search_depth",
                                                                                                    scope=VariableScope.BOTH,
                                                                                                    version=[MySQLVersion.MySQL_57,
                                                                                                             MySQLVersion.MySQL_8],
                                                                                                    dynamic=True,
                                                                                                    read_only=False,
                                                                                                    need_set=True))
    range_optimizer_max_mem_size: SingleValueVariable = field(default_factory=lambda: SingleValueVariable(name="range_optimizer_max_mem_size",
                                                                                                          scope=VariableScope.BOTH,
                                                                                                          version=[MySQLVersion.MySQL_57,
                                                                                                                   MySQLVersion.MySQL_8],
                                                                                                          dynamic=True,
                                                                                                          read_only=False,
                                                                                                          need_set=True))
    version: SingleValueVariable = field(default_factory=lambda: SingleValueVariable(name="version",
                                                                                     scope=VariableScope.BOTH,
                                                                                     version=[MySQLVersion.MySQL_57,
                                                                                              MySQLVersion.MySQL_8],
                                                                                     dynamic=False,
                                                                                     read_only=True,
                                                                                     need_set=False))

    innodb_page_size: SingleValueVariable = field(default_factory=lambda: SingleValueVariable(name="innodb_page_size",
                                                                                     scope=VariableScope.GLOBAL,
                                                                                     version=[MySQLVersion.MySQL_57,
                                                                                              MySQLVersion.MySQL_8],
                                                                                     dynamic=False,
                                                                                     read_only=True,
                                                                                     need_set=False))

    innodb_buffer_pool_size: SingleValueVariable = field(default_factory=lambda: SingleValueVariable(name="innodb_buffer_pool_size",
                                                                                     scope=VariableScope.GLOBAL,
                                                                                     version=[MySQLVersion.MySQL_57,
                                                                                              MySQLVersion.MySQL_8],
                                                                                     dynamic=False,
                                                                                     read_only=True,
                                                                                     need_set=False))

    myisam_max_sort_file_size: SingleValueVariable = field(default_factory=lambda: SingleValueVariable(name="myisam_max_sort_file_size",
                                                                                     scope=VariableScope.GLOBAL,
                                                                                     version=[MySQLVersion.MySQL_57,
                                                                                              MySQLVersion.MySQL_8],
                                                                                     dynamic=False,
                                                                                     read_only=True,
                                                                                     need_set=False))

    def get_all_attributes(self):
        return iter(self.__dict__.items())
