from typing import Dict, Optional
from pydantic import BaseModel, Field
from sub_platforms.sql_opt.common.pydantic_utils import PydanticDataClassJsonMixin
from sub_platforms.sql_opt.pg_meta import PGStatistic,PGStatisticExt

class PGTableStatisticsInfo(BaseModel, PydanticDataClassJsonMixin):
    """ PostgreSQL Table Statistics Information """
    db_name: str
    schema_name: str
    table_name: str
    statistic_dict: Optional[Dict[str, PGStatistic]] = Field(default_factory=dict)
    statistic_ext_dict: Optional[Dict[str, PGStatisticExt]] = Field(default_factory=dict)