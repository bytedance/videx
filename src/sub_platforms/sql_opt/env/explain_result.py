from dataclasses import dataclass
from typing import List

import pandas as pd
from dataclasses_json import dataclass_json

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
        res = [f"id\t{'select_type':>{12}}\t{'table':>{table_max_len}}\t{'key':>{key_max_len}}\tpossible_keys"]
        for in_item in self.explain_items:
            in_item: MySQLExplainItem
            res.append(
                f"{in_item.id}\t{str(in_item.type):>{12}}" 
                f"\t{str(in_item.table):>{table_max_len}}\t" 
                f"{str(in_item.key):>{key_max_len}}\t{in_item.possible_keys}"
            )
        return '\n'.join(res)