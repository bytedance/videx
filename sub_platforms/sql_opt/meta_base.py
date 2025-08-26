from abc import ABC
from enum import Enum
from pydantic import BaseModel, Field
from typing import List, Optional, Any, Union

from sub_platforms.sql_opt.common.pydantic_utils import PydanticDataClassJsonMixin


class BaseTableId(BaseModel, PydanticDataClassJsonMixin):
    pass 

class BaseColumn(BaseModel,PydanticDataClassJsonMixin):
    pass

class BaseIndexColumn(BaseModel, PydanticDataClassJsonMixin):
    pass 

class IndexBasicInfo(BaseModel, PydanticDataClassJsonMixin):
    db_name: Optional[str] = Field(default=None)
    table_name: Optional[str] = Field(default=None)
    columns: Optional[List[BaseIndexColumn]] = Field(default_factory=list)

    def get_column_names(self):
        return [column.name for column in self.columns]

class BaseIndex(IndexBasicInfo, BaseModel, PydanticDataClassJsonMixin):
    pass 

class BaseTable(BaseModel, PydanticDataClassJsonMixin):
    pass 