from enum import Enum
from pydantic import BaseModel, Field
from typing import List, Optional, Any, Union

from sub_platforms.sql_opt.common.pydantic_utils import PydanticDataClassJsonMixin
from sub_platforms.sql_opt.meta import IndexBasicInfo,IndexType

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
        
class PGTable(BaseModel, PydanticDataClassJsonMixin):
    dbname: str
    table_schema: str
    table_name: str

    relpages: int 
    reltuples: float
    relallvisible: int

    


class PGColumn(BaseModel):
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
        if not isinstance(other, PGColumn):
            return NotImplemented
        return (
            self.table_catalog == other.table_catalog and
            self.table_schema == other.table_schema and
            self.table_name == other.table_name and
            self.column_name == other.column_name
        )
    
class PGIndexColumn(BaseModel, PydanticDataClassJsonMixin):
    name: Optional[str] = None  # 可能是表达式，所以可以为空
    #cardinality: Optional[int] = None
    #sub_part: Optional[int] = 0
    expression: Optional[str] = None
    collation: Optional[str] = 'asc'
    column_ref: Optional[PGColumn] = Field(default=None, exclude=True)
    table_id: Optional[PGTableId] = Field(default=None)

    @property
    def is_desc(self):
        return self.collation == 'desc'
    
    @classmethod
    def from_column(cls, column: PGColumn,  collation: str = 'asc',expression: Optional[str] = None):
        return NotImplementedError("This method is not implemented in this context.")
    
    @classmethod
    def simple_column(cls,column_name: str, db_name: str, table_name: str, table_schema: str = 'public',
            collation: str = 'asc',expression: str = None):
        column = PGColumn(
            table_catalog=db_name,
            table_schema=table_schema,
            table_name=table_name,
            column_name=column_name,
            data_type='varchar'
        )
        return cls.from_column(column,collation,expression)

    @property
    def db_name(self):
        if self.table_id is not None:
            return self.table_id.db_name
        if self.column_ref is not None:
            return self.column_ref.db
        return None
    
    @property
    def table_name(self):
        if self.table_id is not None:
            return self.table_id.table_name
        if self.column_ref is not None:
            return self.column_ref.table
        return None
    
    @property
    def schema_name(self):
        if self.table_id is not None:
            return self.table_id.schema_name
        if self.column_ref is not None:
            return self.column_ref.table_schema
        return None

    def __eq__(self, other):
        return self.db_name == other.db_name and self.schema_name == other.schema_name and self.table_name == other.table_name \
            and self.name == other.name and self.expression == other.expression \
            and self.collation == other.collation    

class PGIndex(IndexBasicInfo, BaseModel, PydanticDataClassJsonMixin):
    type: Optional[IndexType] = Field(default=None)
    name: Optional[str] = Field(default=None)
    is_unique: Optional[bool] = Field(default=None)
    is_visible: Optional[bool] = True
    index_type: Optional[str] = None
    
    @property
    def db(self):
        return self.db_name

    @property
    def table(self):
        return self.table_name
    
class PGOpTypeName(Enum):
    pass