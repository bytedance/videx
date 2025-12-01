from typing import List

from sub_platforms.sql_opt.videx.videx_metadata import VidexTableStats
from sub_platforms.sql_opt.videx.model.videx_strategy import VidexModelBase, VidexStrategy
from sub_platforms.sql_opt.videx.model.videx_model_innodb import VidexModelInnoDB
from sub_platforms.sql_opt.videx.videx_metadata import VidexTableStats, VidexDBTaskStats
from sub_platforms.sql_opt.videx.model.videx_strategy import VidexStrategy
from sub_platforms.sql_opt.videx.videx_utils import IndexRangeCond
from sub_platforms.sql_opt.pg_meta import PGTable

class VidexModelPG(VidexModelBase):
    def __init__(self, db_stats: VidexDBTaskStats, **kwargs):
        super().__init__(None, VidexStrategy.postgresql)
        self.videx_db_task_stats: VidexDBTaskStats = db_stats

    def scan_time(self, req_json_item: dict) -> float:
        return 0.0
    def get_memory_buffer_size(self, req_json_item: dict) -> int:
        return -1

    def cardinality(self, idx_range_cond: IndexRangeCond) -> int:
        return 0

    def ndv(self, index_name, field_list: List[str]) -> int:
        return 0

    def get_relation_stats(self, req_json_item: dict) -> dict:
        return None

    def table_block_relation_estimate_size(self, req_json_item: dict) -> dict:
        properties = req_json_item['properties']
        videx_db = properties['dbname'].lower()
        table_name = properties['table_name'].lower()
        table: PGTable = self.videx_db_task_stats.get_table_meta(videx_db, table_name)
        res = {
            "relpages": table.relpages,
            "reltuples": table.reltuples,
            "relallvisible": table.relallvisible,
            "relhasindex": len(table.indexes) > 0,
        }
        return res