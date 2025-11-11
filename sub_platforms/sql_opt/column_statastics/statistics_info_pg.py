from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field, PrivateAttr, PlainSerializer, BeforeValidator
from typing_extensions import Annotated
from sub_platforms.sql_opt.pg_meta import PGStatistic,PGStatisticExt
from sub_platforms.sql_opt.column_statastics.statistics_info_base import BaseTableStatisticsInfo
class PGTableStatisticsInfo(BaseTableStatisticsInfo):
    db_name: str
    schema_name: str
    table_name: str
    statistic_dict: Optional[Dict[str, PGStatistic]] = Field(default_factory=dict)
    statistic_ext_dict: Optional[Dict[str, PGStatisticExt]] = Field(default_factory=dict)
