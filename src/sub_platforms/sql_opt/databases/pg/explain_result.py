import pandas as pd
from typing import List, Optional, Union
from pydantic import BaseModel, Field

from sub_platforms.sql_opt.common.pydantic_utils import PydanticDataClassJsonMixin

class PGExplainItem(BaseModel, PydanticDataClassJsonMixin):
    pass

class PGExplainResult(BaseModel, PydanticDataClassJsonMixin):
    pass
