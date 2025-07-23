"""
Copyright (c) 2024 Bytedance Ltd. and/or its affiliates
SPDX-License-Identifier: MIT
"""

from typing import Dict, List, Optional
from pydantic import BaseModel

from sub_platforms.sql_opt.common.pydantic_utils import PydanticDataClassJsonMixin

# return N_NO_LOAD_ROWS if load_rows is not availabl
UNKNOWN_LOAD_ROWS: int = -1


class SampleFileInfo(BaseModel, PydanticDataClassJsonMixin):
    local_path_prefix: str
    tos_path_prefix: str
    sample_file_dict: Dict[str, Dict[str, List[str]]]
    # to remain the relative table rows between join tables, we only import table data with row of table_load_rows
    # from the sampling parquet data
    table_load_rows: Optional[Dict[str, Dict[str, int]]] = None

    def get_table_load_row(self, db: str, table: str):
        if self.table_load_rows is None \
                or self.table_load_rows.get(db, None) is None \
                or self.table_load_rows.get(db).get(table) is None:
            return -1
        else:
            return self.table_load_rows.get(db).get(table)
