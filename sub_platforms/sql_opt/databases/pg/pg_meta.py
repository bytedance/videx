from enum import Enum
from pydantic import BaseModel, Field
from typing import List, Optional, Any, Union

from sub_platforms.sql_opt.common.pydantic_utils import PydanticDataClassJsonMixin

class PGTableId(BaseModel, PydanticDataClassJsonMixin):
    table_catalog: str       #db name               
    table_schema: str        #schema name       
    table_name: str          #table name   

    def __hash__(self):
        return f'{self.table_catalog}.{self.table_schema}.{self.table_name}'.__hash__()

    def __eq__(self, other):
        if not other:
            return False
        return self.db_name.__eq__(other.db_name) and \
            self.table_name.__eq__(other.table_name) and \
            self.schema_name.__eq__(other.schema_name)

    def __lt__(self, other):
        if self.db_name < other.db_name:
            return True
        elif self.db_name == other.db_name and self.table_name < other.table_name:
            return True
        elif self.db_name == other.db_name and self.table_name == other.table_name and self.schema_name < other.schema_name:
            return True
        else:
            return False
        
class PgColumn(BaseModel):
    table_catalog: str       #db name               
    table_schema: str        #schema name       
    table_name: str          #table name   
    column_name: str                        
    ordinal_position: int                   
    column_default: Optional[str] = None    
    is_nullable: Union[str, bool]           
    data_type: str                          
    character_maximum_length: Optional[int] = None
    character_octet_length: Optional[int] = None
    numeric_precision: Optional[int] = None
    numeric_precision_radix: Optional[int] = None
    numeric_scale: Optional[int] = None
    datetime_precision: Optional[int] = None
    interval_type: Optional[str] = None
    interval_precision: Optional[int] = None
    character_set_catalog: Optional[str] = None
    character_set_schema: Optional[str] = None
    character_set_name: Optional[str] = None
    collation_catalog: Optional[str] = None
    collation_schema: Optional[str] = None
    collation_name: Optional[str] = None
    domain_catalog: Optional[str] = None
    domain_schema: Optional[str] = None
    domain_name: Optional[str] = None
    udt_catalog: Optional[str] = None
    udt_schema: Optional[str] = None
    udt_name: Optional[str] = None
    scope_catalog: Optional[str] = None
    scope_schema: Optional[str] = None
    scope_name: Optional[str] = None
    maximum_cardinality: Optional[int] = None
    dtd_identifier: Optional[str] = None
    is_self_referencing: Optional[Union[str, bool]] = None
    is_identity: Optional[Union[str, bool]] = None
    identity_generation: Optional[str] = None
    identity_start: Optional[str] = None
    identity_increment: Optional[str] = None
    identity_maximum: Optional[str] = None
    identity_minimum: Optional[str] = None
    identity_cycle: Optional[Union[str, bool]] = None
    is_generated: Optional[str] = None
    generation_expression: Optional[str] = None
    is_updatable: Optional[Union[str, bool]] = None

    def __str__(self):
        return f"{self.table_catalog}.{self.table_schema}.{self.table_name}.{self.column_name}"

    def __eq__(self, other):
        if not isinstance(other, PgColumn):
            return NotImplemented
        return (
            self.table_catalog == other.table_catalog and
            self.table_schema == other.table_schema and
            self.table_name == other.table_name and
            self.column_name == other.column_name
        )
    
