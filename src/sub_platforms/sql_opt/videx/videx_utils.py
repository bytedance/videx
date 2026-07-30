# -*- coding: utf-8 -*-
"""
Copyright (c) 2024 Bytedance Ltd. and/or its affiliates
SPDX-License-Identifier: MIT
"""
import json
import logging
import os
import pickle
import re
import socket
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Dict, Union, Tuple, Set, Optional

import msgpack
import numpy as np
import pandas as pd

from sub_platforms.sql_opt.env.rds_env import Env, OpenMySQLEnv
from sub_platforms.sql_opt.meta import TableId, Index, IndexColumn

# VIDEX obtains four statistical information through fetch_all_meta_for_videx.
# All four functions will directly access the original database.
# Especially, ndv and histogram impose a heavy load on the original database.
# Exercise caution: fetch_all_meta_for_videx should not be executed on the online production environment.
VIDEX_IP_WHITE_LIST = [
    '127.0.0.1',
    'localhost',
]


def target_env_available_for_videx(env: Env) -> bool:
    """
    Check whether the given env supports videx to directly collect raw statistical information,
    such as analyze table update histogram, or select count(distinct)
    """
    if not isinstance(env, OpenMySQLEnv):
        return False
    host = env.instance.split(':')[0]
    return host in VIDEX_IP_WHITE_LIST


def construct_involved_db_tables(related_tables: List[Set[TableId]]) -> Dict[str, List[str]]:
    """
    Given a set of TableId, convert it to the form of db->sorted(list(table_name)).
    The table_name has been deduplicated and sorted.
    """
    res = defaultdict(set)
    for table_id_set in related_tables:
        for table_id in table_id_set:
            res[table_id.db_name].add(table_id.table_name)
    sorted_keys = sorted(res.keys())
    sorted_dict = {db: sorted(list(res[db])) for db in sorted_keys}
    return sorted_dict


class BTreeKeyOp(Enum):
    """
    Corresponds to MySQL HaRKeyFunction
    """
    EQ = ("=", "HA_READ_KEY_EXACT")
    GTE = (">=", "HA_READ_KEY_OR_NEXT")
    LTE = ("<=", "HA_READ_KEY_OR_PREV")
    GT = (">", "HA_READ_AFTER_KEY")
    LT = ("<", "HA_READ_BEFORE_KEY")
    HA_READ_PREFIX = ("=x%", "HA_READ_PREFIX")
    HA_READ_PREFIX_LAST = ("last_x%", "HA_READ_PREFIX_LAST")
    HA_READ_PREFIX_LAST_OR_PREV = ("<=last_x%",)
    HA_READ_MBR_CONTAIN = ("HA_READ_MBR_CONTAIN",)
    HA_READ_MBR_INTERSECT = ("HA_READ_MBR_INTERSECT",)
    HA_READ_MBR_WITHIN = ("HA_READ_MBR_WITHIN",)
    HA_READ_MBR_DISJOINT = ("HA_READ_MBR_DISJOINT",)
    HA_READ_MBR_EQUAL = ("HA_READ_MBR_EQUAL",)
    HA_READ_INVALID = ("HA_READ_INVALID",)
    Unknown = ("Unknown",)

    @staticmethod
    def init(value: str):
        """
        Get the HaRKeyFunction enumeration object corresponding to the value or name

        Args:
            value (str):

        Returns:
            BTreeKeyOp: Corresponds to HaRKeyFunction enum item，if missing，return Unknown

        """
        if not hasattr(BTreeKeyOp, "_value_map"):
            BTreeKeyOp._value_map = {}
            for member in BTreeKeyOp:
                for v in member.value:
                    BTreeKeyOp._value_map[v] = member
                    BTreeKeyOp._value_map[member.name] = member
        return BTreeKeyOp._value_map.get(value, BTreeKeyOp.Unknown)


class BTreeKeySide(Enum):
    left = 'left'
    right = 'right'

    @staticmethod
    def from_op(op: Union[str, BTreeKeyOp]):
        if isinstance(op, str):
            op = BTreeKeyOp.init(op)
        if op in [BTreeKeyOp.LT, BTreeKeyOp.EQ]:
            return BTreeKeySide.left
        elif op in [BTreeKeyOp.GT]:
            return BTreeKeySide.right
        else:
            raise ValueError(f"Invalid given btree op: {op}")


@dataclass
class RangeCond:
    """
    Single-column query condition.
    For example, c2 < 3 and c2 > 1, which is converted from the more basic min-key and max-key
    """
    col: str
    data_type: str
    min_value: str = None
    max_value: str = None
    min_op: str = None  # for print，including "None", "=", "<", "<="
    max_op: str = None  # for print，including "None", "=", ">", ">="
    """
    The original operators sent by the MySQL interface doesn't care about min or max, 
    but indicates whether the position of the key appears on the left or right side of the value.
    
    In the original MySQL, `<` or `=` represents "left", and `>` represents "right".
    Some modifications have been made here to facilitate strategy operations:
    1. `<` and `=` are unified as "left".
    2. For the first few columns of a multi-column index, special processing will be done on the `pos_op` 
    corresponding to "=", and it will be unified as "right".
    
    Note that if the first n - 1 columns are not "=", it will make InnoDB search very difficult to understand. 
    Therefore, MySQL also prohibits this situation.
    We now ensure that the case where the first n - 1 columns are "=" is handled correctly, 
    and other cases will be dealt with later.

    """
    min_key_pos_side: BTreeKeySide = None  # None, left, right
    max_key_pos_side: BTreeKeySide = None  # None, left, right

    @staticmethod
    def _check_op_and_side(op: str, is_min: bool):
        if is_min:
            MIN_VALID_OP = {"=", ">", ">="}
            assert op in MIN_VALID_OP, f"Invalid min_op: {op}, valid: {MIN_VALID_OP}"
            # assert side in [BTREE_KEY_SIDE_LEFT, BTREE_KEY_SIDE_RIGHT], f"Invalid min key pos side: {side}"
        else:
            MAX_VALID_OP = {"=", "<", "<="}
            assert op in MAX_VALID_OP, f"Invalid max_op: {op}, valid: {MAX_VALID_OP}"
            # assert side in [BTREE_KEY_SIDE_LEFT, BTREE_KEY_SIDE_RIGHT], f"Invalid max key pos side: {side}"

    def __post_init__(self):
        if self.min_value is not None:
            self._check_op_and_side(self.min_op, is_min=True)
        if self.max_value is not None:
            self._check_op_and_side(self.min_op, is_min=False)

    def add_min(self, op: str, value: str, side: BTreeKeySide):
        self.min_value = value
        self.min_op = op
        self.min_key_pos_side = side
        self._check_op_and_side(self.min_op, is_min=True)

    def add_max(self, op: str, value: str, side: BTreeKeySide):
        self.max_value = value
        self.max_op = op
        self.max_key_pos_side = side
        self._check_op_and_side(self.max_op, is_min=False)

    def valid(self):
        return self.min_op is not None or self.max_op is not None

    def has_min(self):
        return self.min_op is not None

    def has_max(self):
        return self.max_op is not None

    def is_singlepoint(self) -> bool:
        """
        The naming refers to SEL_ARG::is_singlepoint sql/range_optimizer/tree.h:820
        Actually, it is to determine whether it is an equality query.

        Returns:

        """
        return self.min_op == "="

    def __eq__(self, other):
        if not isinstance(other, RangeCond):
            return False
        if not self.valid() or not other.valid():
            return False
        return self.col == other.col and self.min_op == other.min_op and self.max_op == other.max_op \
            and self.min_value == other.min_value and self.max_value == other.max_value

    def all_possible_strs(self) -> List[str]:
        res = []
        REVERSE_OP = {">": "<", ">=": "<="}

        if self.min_op == '=':
            res.append(f"{self.col} = {self.min_value}")
            res.append(f"{self.min_value} = {self.col}")
            # return res
        elif self.min_op is not None and self.max_op is not None:
            # like 2 < col < 3
            rev_min_op = REVERSE_OP.get(self.min_op, "!!!!!")
            rev_max_op = REVERSE_OP.get(self.max_op, "!!!!!")
            res.append(f"{self.min_value} {rev_min_op} {self.col} {self.max_op} {self.max_value}")
            res.append(f"{self.max_op} {rev_max_op} {self.col} {self.min_op}  {self.min_value} ")
            # return res
        elif self.min_op is not None:
            rev_min_op = REVERSE_OP.get(self.min_op, "!!!!!")
            # col < v
            res.append(f"{self.col} {self.min_op} {self.min_value}")
            # v < col
            res.append(f"{self.min_value} {rev_min_op} {self.col}")
        if self.max_op is not None:
            rev_max_op = REVERSE_OP.get(self.max_op, "!!!!!")
            # col > v
            res.append(f"{self.col} {self.max_op} {self.max_value}")
            # v > col
            res.append(f"{self.max_value} {rev_max_op} {self.col}")
            # v > col > 'NULL'
            res.append(f"{self.max_value} {rev_max_op} {self.col} > 'NULL'")
            # 'NULL' < col < v
            res.append(f"'NULL' < {self.col} {self.max_op} {self.max_value}")

        return res

    def __repr__(self):
        res = self.all_possible_strs()
        if res is None or len(res) == 0:
            return "None"
        return res[0]

    def to_print_full(self) -> str:
        res = (f"{self.__repr__()}; "
               f"min_side: {self.min_key_pos_side.value if self.min_key_pos_side else 'None'}, "
               f"max_side: {self.max_key_pos_side.value if self.max_key_pos_side else 'None'}")
        return res

    @staticmethod
    def construct_eq(col: str, data_type: str, value: str) -> 'RangeCond':
        return RangeCond(col=col, data_type=data_type,
                         min_value=value, min_op="=", min_key_pos_side=BTreeKeySide.left,
                         max_value=value, max_op="=", max_key_pos_side=BTreeKeySide.right,
                         )


@dataclass
class IndexRangeCond:
    """
    For example, ranges = [RangeCond(c1 = 3), RangeCond(c2 < 3 and c2 > 1)]

    Translate handler:: records_in_range to List[RangeCond].
    The above example is converted from the more basic min-key and max-key.

    """
    index_name: str
    ranges: List[RangeCond]

    def ranges_to_str(self):
        return " AND ".join(map(str, self.ranges))

    def __repr__(self):
        return f"{self.index_name}: {self.ranges_to_str()}"

    def to_print_full(self) -> str:
        return f"{self.index_name}: " + " AND ".join(map(lambda k: k.to_print_full(), self.ranges))

    def __eq__(self, other):
        if not isinstance(other, IndexRangeCond):
            return False
        return self.index_name == other.index_name and self.ranges == other.ranges

    @staticmethod
    def from_dict(min_key: dict, max_key: dict, get_data_type: callable = None,
                  index_meta: Index = None,
                  ) -> 'IndexRangeCond':
        """
        Examples:

        EXPLAIN select I_PRICE from ITEM where I_IM_ID = 3
        KEY: idx_I_IM_ID   MIN_KEY: { =  I_IM_ID(3), }, MAX_KEY: { >  I_IM_ID(3), }

        req_json = {"item_type": "videx_request",
                    "properties": {"dbname": "tpcc",
                                   "function": "virtual ha_rows ha_innobase::records_in_range(uint, key_range*, key_range*)",
                                   "table_name": "ITEM",
                                   "target_storage_engine": "INNODB"}, "data": [
                {"item_type": "min_key",
                 "properties": {"index_name": "idx_I_IM_ID", "length": "4", "operator": "="},
                 "data": [
                     {"item_type": "column_and_bound", "properties": {"column": "I_IM_ID", "value": "3"}, "data": []}]},
                {"item_type": "max_key",
                 "properties": {"index_name": "idx_I_IM_ID", "length": "4", "operator": ">"},
                 "data": [{"item_type": "column_and_bound", "properties": {"column": "I_IM_ID", "value": "3"},
                           "data": []}]}]}

            min_key, max_key = req_json['data']

        Args:
            min_key:
            max_key:

        Returns: List[RangeCond]
        """
        # TODO consider desc index when generating IndexRangeCond
        if get_data_type is None:
            get_data_type = lambda x: "Unknown"
        if 'index_name' in min_key['properties']:
            index_name = min_key['properties']['index_name']
        elif 'index_name' in max_key['properties']:
            index_name = max_key['properties']['index_name']
        else:
            index_name = 'INVALUD !!!'
        res = IndexRangeCond(index_name=index_name, ranges=[])

        n_col = max(len(min_key['data']), len(max_key['data']))
        if abs(len(min_key['data']) - len(max_key['data']) > 1):
            # It's abnormal，the delta between min_key and max_key is at most 1
            logging.error("min_key and max_key length can only differ by 1."
                          f"given min_key: {min_key}, max_key: {max_key}")
            return res

        for c in range(n_col):
            is_desc_idx_col = False
            if index_meta and len(index_meta.columns) > c:
                index_col_meta = index_meta.columns[c]
                if index_col_meta.is_desc:
                    is_desc_idx_col = True

            # col = min_key['data'][c]["properties"]['column']
            # value = min_key['data'][c]["properties"]['value']
            # res.ranges.append(RangeCond.construct_eq(col, get_data_type(col), value))
            has_min = c < len(min_key['data'])
            has_max = c < len(max_key['data'])
            if has_min:
                col = min_key['data'][c]["properties"]['column']
            elif has_max:
                col = max_key['data'][c]["properties"]['column']
            else:
                logging.error(f"receive boundary without min and max: min_key: {min_key}, max_key: {max_key}")
                return res

            min_op = min_key['properties']['operator'] if has_min else None
            max_op = max_key['properties']['operator'] if has_max else None
            min_value = min_key['data'][c]["properties"]['value'] if has_min else None
            max_value = max_key['data'][c]["properties"]['value'] if has_max else None
            # refer to SEL_ARG::is_singlepoint
            if has_min and has_max and min_value == max_value:
                # =
                res.ranges.append(RangeCond.construct_eq(col, data_type=get_data_type(col), value=min_value))
            else:
                last_range = RangeCond(col=col, data_type=get_data_type(col))
                # add min bound
                if has_min:
                    if min_op == "=":
                        if not is_desc_idx_col:
                            # >= min_value.
                            last_range.add_min(">=", min_value, BTreeKeySide.left)
                        else:
                            # c >= v -> c <= v
                            last_range.add_max("<=", min_value, BTreeKeySide.right)
                    elif min_op == ">":
                        if not is_desc_idx_col:
                            last_range.add_min(">", min_value, BTreeKeySide.right)
                        else:
                            # c > v -> c < v
                            last_range.add_max("<", min_value, BTreeKeySide.left)
                    else:
                        pass
                # add max bound
                if has_max:
                    if max_op == ">":
                        if not is_desc_idx_col:
                            # <= max_value
                            last_range.add_max("<=", max_value, BTreeKeySide.right)
                        else:
                            last_range.add_min(">=", max_value, BTreeKeySide.left)
                    elif max_op == "<":
                        if not is_desc_idx_col:
                            last_range.add_max("<", max_value, BTreeKeySide.left)
                        else:
                            last_range.add_min(">", max_value, BTreeKeySide.right)
                    else:
                        pass
                res.ranges.append(last_range)
        return res

    def match(self, range_str: str, ignore_range_after_neq: bool) -> bool:
        """

        Args:
            range_str:
            ignore_range_after_neq: In the case of a multi-column query in btree, if the first column is not an equality,
                the subsequent columns will be ignored, so there is no match here either.
            @See sub_platforms.sql_opt.videx.strategy.VidexModelInnoDB.__init__
        Returns:

        """
        gt_range_str_list = range_str.split(' AND ')
        cmp_ranges = self.get_valid_ranges(ignore_range_after_neq)

        if len(gt_range_str_list) != len(cmp_ranges):
            return False
        for cond, gt_range_str in zip(cmp_ranges, gt_range_str_list):
            all_strs = cond.all_possible_strs()
            if gt_range_str.strip() not in all_strs:
                return False
        return True

    def get_valid_ranges(self, ignore_range_after_neq: bool) -> List[RangeCond]:
        """

        Args:
            ignore_range_after_neq: In the case of a multi-column query in btree, if the first column is not an equality,
                the subsequent columns will be ignored, so there is no match here either.
                @See sub_platforms.sql_opt.videx.strategy.VidexModelInnoDB.__init__
        Returns:

        """
        ranges = []
        if ignore_range_after_neq:
            # 从 0 向后找，找到第一个非等值列。保留等值列和第一个非等值列，抛弃后续的 ranges
            for range_cond in self.ranges:
                ranges.append(range_cond)
                if not range_cond.is_singlepoint():
                    break
        else:
            ranges = self.ranges
        return ranges


@dataclass
class GT_Table_Return:
    """
    Input a list of gt rec_in_ranges, which is parsed from the trace.
    It contains all the gt in a table. This is for debugging and used to compare the online effects.

    Refer to：sub_platforms.sql_opt.videx.metadata.extract_rec_in_range_gt_from_explain
    Args:
        gt_rec_in_ranges: {
            "idx_1": [
                {"range_str": "'1995-01-01' <= O_ORDERDATE <= '1996-12-31'", "rows": 1282},
                {"range_str": "P_TYPE < 5", "rows": 123},
            ],
            "idx_2": [
                {"range_str": "O_ORDERDATE < '1995-01-01'", "rows": 1282},
                {"range_str": "P_TYPE >= 5", "rows": 123},
            ]
        }
    """
    idx_gt_pair_dict: Dict[str, list] = field(default_factory=lambda: defaultdict(list))

    @staticmethod
    def parse_raw_gt_rec_in_range_list(raw_gt_rec_in_range_list: List[dict]) -> Dict[str, 'GT_Table_Return']:
        """

        Returns:
            Dict[str, GT_Table_Return]: table -> GT_Table_Return
        """
        gt_rr_dict = defaultdict(GT_Table_Return)
        for rr in raw_gt_rec_in_range_list:
            """
              {
                "table": "`nation` `n1`"
                "index": "1_2_idx_I_IM_ID", 
                "ranges": ["I_IM_ID = 70","I_IM_ID = 80"],
                "rows": 21, "cost": 3.12041, 
              }
            """
            if "ranges" not in rr:
                continue
            index_name = rr["index"]
            # len > 1的话，意味着 gt_rr 包含 or 或者 in 条件，按照均匀分布推导出 rows
            per_rows = int(rr["rows"]) / len(rr["ranges"])

            tables = rr["table"].split(" ")
            for table in tables:
                table = table.strip('`').lower()
                for ranges_str in rr["ranges"]:
                    gt_rr_dict[table].idx_gt_pair_dict[index_name].append({"range_str": ranges_str, "rows": per_rows})
        return gt_rr_dict

    def find(self, range_cond: IndexRangeCond, ignore_range_after_neq: bool = True) -> Union[int, None]:
        """

        Args:
            range_cond:
            ignore_range_after_neq:

        Returns:

        """
        ranges_str = range_cond.ranges_to_str()
        if range_cond.index_name in self.idx_gt_pair_dict:
            gt_index_ranges = self.idx_gt_pair_dict[range_cond.index_name]
            for gt_item in gt_index_ranges:
                # gt_item: {"range_str": ranges_str, "rows": per_rows}
                if range_cond.match(gt_item["range_str"], ignore_range_after_neq):
                    return int(gt_item["rows"])

            logging.warning(f"NOGT: rec_in_ranges. found index but not gt."
                            f"given index: {range_cond.index_name}, given range: {ranges_str}, "
                            f"gt ranges: {gt_index_ranges}")
        else:
            logging.warning(f"NOGT: rec_in_ranges. index not in gt. "
                            f"given index: {range_cond.index_name}, given range: {ranges_str}, "
                            f"gt index keys: {list(self.idx_gt_pair_dict.keys())}")


def str_lower_eq(a, b):
    return str(a).lower() == str(b).lower()


def add_dict_to_json_file(all_json_file, new_dict, indent=4):
    """
    The all_json_file is a dictionary, in the form of {"k1": v1, "k2": v2,...}
    new_dict is in the form of {"k3": v3, "k4": v4,...}
    After merging, it is in the form of {"k1": v1, "k2": v2, "k3": v3, "k4": v4,...}
    Then write it to the file.

    Args:
        all_json_file:
        new_dict:
        indent:

    Returns:

    """
    with open(all_json_file, "r") as f1:
        all_dict = json.load(f1)
    all_dict.update(new_dict)
    with open(all_json_file, "w") as f:
        json.dump(all_dict, f, indent=indent)


def add_dict_to_pickle_file(all_pickle_file, new_dict: dict):
    """
    The pickle file is a dictionary, in the form of {"k1": v1, "k2": v2,...}
    new_dict 形如 {"k3": v3, "k4": v4,...}
    After merging, it is in the form of {"k1": v1, "k2": v2, "k3": v3, "k4": v4,...}
    Then write it to the file.

    Args:
        all_pickle_file:
        new_dict:

    Returns:

    """

    with open(all_pickle_file, 'rb') as f:
        all_dict = pickle.load(f)
    all_dict.update(new_dict)
    with open(all_pickle_file, 'wb') as f:
        pickle.dump(all_dict, f)


def load_msgpack_from_file(filename: str):
    if not os.path.exists(filename):
        return None

    with open(filename, 'rb') as file_in:
        read_data = file_in.read()
    data = msgpack.unpackb(read_data)
    return data


def dump_msgpack_to_file(filename: str, data: Union[dict, list]):
    parent_path = os.path.dirname(os.path.abspath(filename))
    if not os.path.exists(parent_path):
        os.makedirs(parent_path)

    packed_data = msgpack.packb(data)
    with open(filename, 'wb') as file_out:
        file_out.write(packed_data)


def load_json_from_file(filename: str):
    if not os.path.exists(filename):
        return None

    with open(filename, 'r') as file:
        data = json.load(file)
    return data


def dump_json_to_file(filename: str, data: Union[dict, list], indent: int = 4):
    parent_path = os.path.dirname(os.path.abspath(filename))
    if not os.path.exists(parent_path):
        os.makedirs(parent_path)

    with open(filename, 'w') as file:
        json.dump(data, file, indent=indent)


def load_data_from_file(filename: str, serial_func: str = "json"):
    """Universal loading data function
    Args:
        filename:
        serial_func: support json or msgpack

    Returns:
        the content of filename
    """
    if serial_func.lower() == "json":
        result = load_json_from_file(filename)
    elif serial_func.lower() == "msgpack":
        result = load_msgpack_from_file(filename)
    else:
        raise NotImplementedError(f"{serial_func} not support")
    return result


def dump_data_to_file(filename: str, data: Union[dict, list], serial_func: str = "json", **kwargs):
    """Universal dumping data function
    Args:
        filename:
        data: data that need to save to file
        serial_func: support json or msgpack
        **kwargs: serial_func that named json can accept indent parameter

    """
    if serial_func.lower() == "json":
        dump_json_to_file(filename, data, **kwargs)
    elif serial_func.lower() == "msgpack":
        dump_msgpack_to_file(filename, data)
    else:
        raise NotImplementedError(f"{serial_func} not support")


def fetch_create_table_ddls(env: Env, target_db: str, table_names: List[str], new_engine: str = None) -> Dict[str, str]:
    """
    Extract the show create table statements of the given tables. Return a dictionary of table names and DDLs.
    Args:
        env:
        target_db:
        table_names:
        new_engine:

    Returns:
        Return a dictionary with lowercase keys: lower(table_name) -> ddl;

    """
    env._switch_db(target_db)
    try:
        res = {}
        for table_name in table_names:
            result = env.execute("SHOW CREATE TABLE `{}`".format(table_name))
            if len(result) == 0:
                logging.warning(f"table {table_name} not exists")
                continue
            table_name, ddl = result[0]

            if new_engine is not None:
                ddl = re.sub(r"ENGINE=\w+", "ENGINE={}".format(new_engine), ddl)

            res[table_name.lower()] = ddl
    finally:
        env._switch_db(env.default_db)
    return res


class TestHandler(logging.Handler):
    """
    Detect whether the Python logging module has generated error logs by creating a custom logging handler.

    Examples:
        def setUp(self) -> None:
            self.test_handler = TestHandler()
            self.root_logger = logging.getLogger()  # Get the root logger
            self.root_logger.addHandler(self.test_handler)

        def tearDown(self) -> None:
            self.root_logger.removeHandler(self.test_handler)

        def test_logging_error():
            # Your test code that may log errors goes here
            logging.error('This is an error message')  # Using logging.error instead of logger.error

            # Check if any error logs were created
            assert len(handler.error_logs) == 1
    """

    def __init__(self):
        super().__init__()
        self.error_logs = []

    def emit(self, record):
        if record.levelno == logging.ERROR:
            self.error_logs.append(record)


def compare_explain(expect: List[Dict], actual: List[Dict]):
    """
    Compare two explains and return the score, a brief message, and detailed differences.
    Args:
        expect:
        actual:

    Returns:

    """
    if len(expect) != len(actual):
        return {
            "score": 0.0,
            "msg": "length of explain items in expect and actual do not match.",
            "diff": {}
        }

    def compare_keys(explain_a, explain_b, key):
        if key in ['ref']:
            ref_a, ref_b = explain_a[key] if explain_a.get(key) else '', explain_b[key] if explain_b.get(key) else ''
            # 去掉 db name
            table_name_a, table_name_b = ref_a.split('.')[-1], ref_b.split('.')[-1]
            if ref_a != ref_b and table_name_a == table_name_b == '':
                return False, ref_a, ref_b
            return table_name_a == table_name_b, ref_a, ref_b
        if key == "possible_keys":
            keys_a = explain_a.get(key, "").split(',') if explain_a.get(key) else []
            keys_b = explain_b.get(key, "").split(',') if explain_b.get(key) else []
            return len(keys_a) == len(keys_b), keys_a, keys_b
        if key == "rows":
            rows_a = float(explain_a.get(key, 0))
            rows_b = float(explain_b.get(key, 0))
            if rows_a < 10 and rows_b < 10:
                return True, rows_a, rows_b
            # regard as same if < 15
            return abs(rows_a - rows_b) <= max(15., 0.1 * max(rows_a, rows_b)), rows_a, rows_b
        return explain_a.get(key) == explain_b.get(key), explain_a.get(key), explain_b.get(key)

    matched_count = 0
    diffs = {}
    first_mismatch_msg = ""
    keys_to_compare = ['table', 'select_type', 'type', 'ref', 'key', 'key_len', 'possible_keys', 'rows']

    for idx, (e_item, a_item) in enumerate(zip(expect, actual)):
        item_diffs = {}
        item_match = True

        for key in keys_to_compare:
            match, e_value, a_value = compare_keys(e_item, a_item, key)
            if not match:
                item_match = False
                item_diffs[key] = {"expected": e_value, "actual": a_value}
                if not first_mismatch_msg:  # Record the first mismatch message
                    first_mismatch_msg = f"item={idx}, id={e_item['id']}, " \
                                         f"actual: {key}={a_value}, expected: {key}={e_value}"

        if item_match:
            matched_count += 1
        else:
            diffs[idx] = item_diffs

    score = matched_count / len(expect) if expect else 0.0

    return {
        "score": score,
        "msg": first_mismatch_msg,
        "diff": diffs
    }


def search_videx_http_dict(videx_trace) -> Tuple[List[Dict], List[Dict]]:
    success_true = []
    success_false = []

    # Recursive function to traverse
    def traverse(obj):
        if isinstance(obj, dict):
            if obj.get("dict_name") == "videx_http":
                # Check success status and append to the appropriate list
                if obj.get("success") is True:
                    success_true.append(obj)
                elif obj.get("success") is False:
                    success_false.append(obj)
            for value in obj.values():
                traverse(value)
        elif isinstance(obj, list):
            for item in obj:
                traverse(item)

    traverse(videx_trace)

    return success_true, success_false


def data_type_is_int(data_type: str) -> bool:
    # mysql int contains "TINYINT", "SMALLINT", "MEDIUMINT", "INT", "INTEGER", "BIGINT",
    return 'INT' in data_type.upper()


def reformat_datetime_str(datetime_input: Union[str, int], fmt='%Y-%m-%d %H:%M:%S.%f') -> str:
    """
    Args:
        datetime_input:
        fmt:

    Returns:

    """
    if isinstance(datetime_input, str) and datetime_input == 'NULL':
        return datetime.min.strftime(fmt)
    return datetime.strftime(parse_datetime(datetime_input), fmt)


def parse_datetime(datetime_input: Union[str, int]) -> datetime:
    """
    Convert a string or an integer to a datetime object. It can handle MySQL date and datetime formats,
    as well as integer timestamps (in seconds or nanoseconds).
    Args:
        datetime_input: A string or an integer representing a date/time or a timestamp.
    Returns:
        datetime: The corresponding datetime object.
    Raises:
        ValueError: If the input is neither in a date/time format nor an integer timestamp, an exception will be raised.。
    """
    if isinstance(datetime_input, str):
        datetime_str = datetime_input.strip('\'"')

        try:
            datetime_int = int(datetime_str)
            return parse_timestamp(datetime_int)
        except ValueError:
            pass
    elif isinstance(datetime_input, int):
        return parse_timestamp(datetime_input)
    else:
        raise ValueError("Input must be a string or an integer")

    for fmt in ('%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f', "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(datetime_str, fmt)
        except ValueError:
            continue

    raise ValueError("No suitable format found for '{}'".format(datetime_input))


from datetime import datetime, timedelta


def parse_timestamp(timestamp):
    """
    convert int timestamp into datetime
    """
    length = len(str(timestamp))
    if length <= 10:
        return datetime.fromtimestamp(timestamp)
    elif length <= 13:
        milliseconds = timestamp % 1_000
        return datetime.fromtimestamp(timestamp // 1_000).replace(microsecond=milliseconds * 1000)
    elif length <= 16:
        microseconds = timestamp % 1_000_000
        return datetime.fromtimestamp(timestamp // 1_000_000).replace(microsecond=microseconds)
    elif length <= 19:
        nanoseconds = timestamp % 1_000_000_000
        base_datetime = datetime.fromtimestamp(timestamp // 1_000_000_000)
        return base_datetime + timedelta(microseconds=nanoseconds // 1000)
    else:
        raise ValueError("Integer timestamp length is not compatible: '{}'".format(timestamp))


def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Try private network broadcast address first
        try:
            s.connect(('10.255.255.255', 1))
            ip = s.getsockname()[0]
        except Exception:
            # Fallback to Google's DNS if private network fails
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'  # Fallback to localhost if all attempts fail
    finally:
        s.close()
    return ip


def join_path(base: str, relative: str) -> str:
    """
    Join absolute path by joining a base path with a relative path.
    The base can be either a file path (e.g. __file__) or a directory path.

    Args:
        base: Base path to resolve from. Can be:
            - A file path (e.g. __file__)
            - A directory path
        relative: Path relative to the base path

    Returns:
        str: Resolved absolute path

    Examples:
        >>> # When base is a file
        >>> join_path(__file__, '../data/test.txt')
        '/absolute/path/to/data/test.txt'

        >>> # When base is a directory
        >>> join_path('/path/to/dir', 'data/test.txt')
        '/path/to/dir/data/test.txt'
    """
    if os.path.isdir(base):
        return os.path.join(base, relative)
    return os.path.join(os.path.dirname(base), relative)


def get_func_with_parent(func):
    """
    Return function name directly if module is None or empty (e.g. built-in functions)
    Args:
        func:

    Returns:

    """

    if not func.__module__:
        return func.__name__
    # e.g. 'foo.bar.utils.function_name' -> 'utils.function_name'
    module = func.__module__.split('.')[-1]
    return f"{module}.{func.__name__}"


def is_datetime_like(series):
    """
    check whether series is a datetime like
    including：pandas/numpy datetime64、pandas Period、Python datetime/date
    Note: for data like pd.Series([date(2023, 1, 1), date(2023, 1, 2)]), its dtype is object,
    so we need to check the first non-empty value to determine whether it is a datetime like.
    """
    if pd.api.types.is_datetime64_any_dtype(series) or pd.api.types.is_period_dtype(series):
        return True

    if series.dtype == 'object' and len(series) > 0:
        # get the first non-empty value
        sample = next((x for x in series if x is not None and pd.notna(x)), None)
        if sample is not None:
            from datetime import datetime, date
            return isinstance(sample, (datetime, date))

    return False


def safe_tolist(series: pd.Series) -> list:
    """
    Safely convert a pandas Series to a Python list, with optimized performance.

    Uses Series.tolist() for non-datetime types for better performance, only applies
    safe conversion when datetime64 values are present.

    Args:
        series (pd.Series): Input pandas Series of any dtype

    Returns:
        list: A Python list preserving original values and proper datetime conversion

    Examples:
        >>> series = pd.Series([np.datetime64('2000-01-01'), 1, 'string'])
        >>> safe_tolist(series)
        [datetime.datetime(2000, 1, 1, 0, 0), 1, 'string']
    """
    # Fast path for safe types
    if not is_datetime_like(series):
        return series.values.tolist()

    # Safe conversion for datetime64
    def safe_convert(val):
        if isinstance(val, np.datetime64):
            return pd.Timestamp(val).to_pydatetime()
        return val

    return [safe_convert(x) for x in series.values]

def get_column_data_type(column_type: str):
    """
    convert mysql data type to inner type
    """
    data_type = None
    if 'int' in column_type:
        data_type = 'int'
    elif column_type == 'float':
        data_type = 'float'
    elif column_type == 'double':
        data_type = 'double'
    elif column_type == 'decimal':
        data_type = 'decimal'
    elif column_type in ['date', 'timestamp']:
        data_type = 'date'
    elif column_type == 'datetime':
        # histogram 需要区分 datetime 和 date，因为 videx find_nearest_buckets 会用到
        data_type = 'datetime'
    elif column_type in ['string', 'varchar', 'char', 'text', 'longtext']:
        data_type = 'string'
    elif column_type == 'json':
        data_type = 'json'
    return data_type

def pg_serialize_schema_table(schema: str, table: str) -> str:
    """
    convert schema_name and table_name to 'schema.table'
    """
    if not schema or not table:
        raise ValueError("Schema and table names must be non-empty.")
    
    return f"{schema.strip()}.{table.strip()}"

def pg_deserialize_schema_table(full_name: str) -> Tuple[str, str]:
    """
    parse 'schema.table' to (schema, table)。
    """
    if '.' not in full_name:
        raise ValueError(f"Invalid format: '{full_name}'. Expected 'schema.table' format.")
    
    parts = full_name.split('.', 1)
    schema = parts[0].strip()
    table = parts[1].strip()
    
    if not schema or not table:
        raise ValueError(f"Schema or table is empty in: '{full_name}'")
    
    return schema, table

if __name__ == '__main__':
    pass
