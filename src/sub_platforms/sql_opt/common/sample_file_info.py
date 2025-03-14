"""
Copyright (c) 2024 Bytedance Ltd. and/or its affiliates
SPDX-License-Identifier: MIT

@ author: bytebrain
@ date: 2025-03-13

"""

from dataclasses import dataclass
from typing import Dict, List

from dataclasses_json import dataclass_json

# 当计算 load_rows 失败时，返回 N_NO_LOAD_ROWS。即不能确定导入行数，全部导入
UNKNOWN_LOAD_ROWS: int = -1


@dataclass_json
@dataclass
class SampleFileInfo:
    local_path_prefix: str
    tos_path_prefix: str
    sample_file_dict: Dict[str, Dict[str, List[str]]]
    # 为保持 join table 相对大小，在 sampling pq 基础上，只导入 table_load_rows 行数据
    table_load_rows: Dict[str, Dict[str, int]] = None

    def get_table_load_row(self, db: str, table: str):
        if self.table_load_rows is None \
                or self.table_load_rows.get(db, None) is None \
                or self.table_load_rows.get(db).get(table) is None:
            return -1
        else:
            return self.table_load_rows.get(db).get(table)
