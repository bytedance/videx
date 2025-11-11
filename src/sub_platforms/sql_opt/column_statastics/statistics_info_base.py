from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field, PrivateAttr, PlainSerializer, BeforeValidator
from typing_extensions import Annotated

from sub_platforms.sql_opt.common.pydantic_utils import PydanticDataClassJsonMixin

class BaseTableStatisticsInfo(BaseModel, PydanticDataClassJsonMixin):
    pass 