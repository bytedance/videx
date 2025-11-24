from pydantic import BaseModel
from sub_platforms.sql_opt.common.pydantic_utils import PydanticDataClassJsonMixin

class BaseTableStatisticsInfo(BaseModel, PydanticDataClassJsonMixin):
    pass 