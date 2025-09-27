"""
Copyright (c) 2024 Bytedance Ltd. and/or its affiliates
SPDX-License-Identifier: MIT
"""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field, PlainSerializer, BeforeValidator
from typing import List, Dict, Tuple, Optional, Union, Any
from pandas import DataFrame
import json

from sub_platforms.sql_opt.common.pydantic_utils import PydanticDataClassJsonMixin

# return N_NO_LOAD_ROWS if load_rows is not availabl
UNKNOWN_LOAD_ROWS: int = -1

def serialize_dataframe(df: DataFrame) -> Dict[str, Any]:
    """将 DataFrame 序列化为字典"""
    if df is None:
        return None
    return {
        'data': df.to_dict('records'),  # 转换为记录列表
        'columns': df.columns.tolist(),
        'index': df.index.tolist()
    }

def deserialize_dataframe(data: Dict[str, Any]) -> DataFrame:
    """从字典反序列化为 DataFrame"""
    if data is None:
        return None
    return DataFrame(data['data'], columns=data['columns'], index=data['index'])



class SampleFileInfo(BaseModel, PydanticDataClassJsonMixin):
    model_config = {"arbitrary_types_allowed": True}

    local_path_prefix: str
    tos_path_prefix: str
    # sample_file_dict: Dict[str, Dict[str, List[str]]]
    sample_file_dict: Dict[str, Any] = Field(
        default_factory=dict,
        serialization_alias='sample_file_dict',
        json_schema_extra={
            'description': 'Dictionary mapping table names to sample data (DataFrame or dict)'
        }
    )
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

    def model_post_init(self, __context: Any) -> None:
        """在初始化后处理 DataFrame 对象"""
        if self.sample_file_dict:
            # 将 DataFrame 对象转换为可序列化的格式
            serializable_dict = {}
            for table_name, data in self.sample_file_dict.items():
                if isinstance(data, DataFrame):
                    serializable_dict[table_name] = serialize_dataframe(data)
                else:
                    serializable_dict[table_name] = data
            self.sample_file_dict = serializable_dict
    
    def get_dataframe(self, table_name: str) -> Optional[DataFrame]:
        """获取指定表的 DataFrame 对象"""
        if table_name not in self.sample_file_dict:
            return None
        
        data = self.sample_file_dict[table_name]
        if isinstance(data, DataFrame):
            return data
        elif isinstance(data, dict) and 'data' in data:
            return deserialize_dataframe(data)
        else:
            return None