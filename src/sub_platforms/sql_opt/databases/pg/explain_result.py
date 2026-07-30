from pydantic import BaseModel

from sub_platforms.sql_opt.common.pydantic_utils import PydanticDataClassJsonMixin

class PGExplainItem(BaseModel, PydanticDataClassJsonMixin):
    pass

class PGExplainResult(BaseModel, PydanticDataClassJsonMixin):
    pass
