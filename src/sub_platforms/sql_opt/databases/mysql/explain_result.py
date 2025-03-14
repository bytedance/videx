"""
Copyright (c) 2024 Bytedance Ltd. and/or its affiliates
SPDX-License-Identifier: MIT

@ author: bytebrain
@ date: 2025-03-13

"""

from dataclasses import dataclass, field
from typing import List, Optional

import pandas as pd
from dataclasses_json import dataclass_json, config


@dataclass_json
@dataclass
class MySQLExplainItem:
    id: int = None
    select_type: str = None
    table: str = None
    partitions: str = None
    type: str = None
    possible_keys: str = None
    key: str = None
    key_len: int = None
    ref: str = None
    rows: int = None
    filtered: int = None
    extra: str = None

@dataclass_json
@dataclass
class MySQLExplainResult:
    format: str = None  # json or None
    # if format is None, result fill in explain_items
    explain_items: List[MySQLExplainItem] = None
    # if format is json, fill the explain_json
    explain_json: dict = None
    trace_dict: Optional[dict] = field(default=None,
                                       metadata=config(exclude=lambda x: True, metadata={'skip_dumps': True}))

    @staticmethod
    def from_df(explain_df: pd.DataFrame) -> 'MySQLExplainResult':
        """
        基于 df-like 的结果构造 MySQLExplainResult
        """
        result = MySQLExplainResult()
        result.format = None
        result.explain_items = []
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

            result.explain_items.append(item)
        return result

    def to_print(self, explain_format='normal'):
        """将 explain result 按照 MySQL output 的样子打印出来

        Args:
            explain_format (str, optional): [normal, tree, json]. Defaults to 'normal'.
        """
        if explain_format not in ['normal']:
            raise NotImplementedError(f"{explain_format} haven't supported")
        if len(self.explain_items) == 0:
            return "empty explain result"

        key_max_len = max(len(str(it.key)) for it in self.explain_items) + 1
        table_max_len = max(len(str(it.table)) for it in self.explain_items) + 1
        key_len_max = max(len(str(it.key_len)) for it in self.explain_items) + 1
        ref_max_len = max(len(str(it.ref)) for it in self.explain_items) + 1
        rows_max_len = max(len(str(it.rows)) for it in self.explain_items) + 1
        filtered_max_len = max(len(str(it.filtered)) for it in self.explain_items) + 1
        extra_max_len = max(len(str(it.extra)) for it in self.explain_items) + 1

        res = [f"id\t{'select_type':>{12}}\t{'table':>{table_max_len}}\t{'key':>{key_max_len}}\t"
               f"{'key_len':>{key_len_max}}\t{'ref':>{ref_max_len}}\t{'rows':>{rows_max_len}}\t"
               f"{'filtered':>{filtered_max_len}}\t{'extra':>{extra_max_len}}\tpossible_keys"]

        for in_item in self.explain_items:
            in_item: MySQLExplainItem
            res.append(
                f"{in_item.id}\t{str(in_item.type):>{12}}"
                f"\t{str(in_item.table):>{table_max_len}}\t"
                f"{str(in_item.key):>{key_max_len}}\t"
                f"{str(in_item.key_len):>{key_len_max}}\t"
                f"{str(in_item.ref):>{ref_max_len}}\t"
                f"{str(in_item.rows):>{rows_max_len}}\t"
                f"{str(in_item.filtered):>{filtered_max_len}}\t"
                f"{str(in_item.extra):>{extra_max_len}}\t"
                f"{in_item.possible_keys}"
            )
        return '\n'.join(res)
