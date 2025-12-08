import logging
import json
from typing import List

from sub_platforms.sql_opt.videx.videx_metadata import VidexTableStats
from sub_platforms.sql_opt.videx.model.videx_strategy import VidexModelBase, VidexStrategy
from sub_platforms.sql_opt.videx.model.videx_model_innodb import VidexModelInnoDB
from sub_platforms.sql_opt.videx.videx_metadata import VidexDBTaskStats
from sub_platforms.sql_opt.videx.videx_pg_metadata import PGVidexTableStats
from sub_platforms.sql_opt.videx.model.videx_strategy import VidexStrategy
from sub_platforms.sql_opt.videx.videx_utils import IndexRangeCond
from sub_platforms.sql_opt.pg_meta import PGTable

class VidexModelPG(VidexModelBase):
    def __init__(self, table_stats: PGVidexTableStats, **kwargs):
        super().__init__(None, VidexStrategy.postgresql)
        self.table_stats: PGVidexTableStats = table_stats

    def scan_time(self, req_json_item: dict) -> float:
        # no used in pg
        return 0.0

    def get_memory_buffer_size(self, req_json_item: dict) -> int:
        # no used in pg
        return -1

    def info_low(self, req_json_item: dict) -> int:
        # no used in pg
        return 0

    def cardinality(self, idx_range_cond: IndexRangeCond) -> int:
        return 0

    def ndv(self, index_name, field_list: List[str]) -> int:
        if len(field_list) == 1:
            colname = field_list[0]
            col_stats_info = self.table_stats.table_statistic.statistic_dict.get(colname)
            if col_stats_info is not None:
                return int(col_stats_info.stadistinct)
            else:
                return 0
        else:
            #TODO: try to fetch from pg_statistic_ext for multi-column NDV,
            # moreover, support ndv learned model (eg: PLM4NDV)
            return 0

    def get_relation_stats(self, req_json_item: dict) -> dict:
        if self.table_stats.table_statistic is None:
            logging.warning(f"Table statistic is None for "
                            f"db_name: {self.table_stats.table_meta.dbname}, "
                            f"table_name: {self.table_stats.table_meta.table_name}")
            return {}
        data_items = req_json_item.get("data")
        if isinstance(data_items, list):
            for item in data_items:
                if item.get("item_type") == "colname":
                    colname = (item.get("properties") or {}).get("name")
                    if colname:
                        break
        if not colname:
            logging.warning("Column name missing in request: %s", req_json_item)
            return {}    
        col_stats_info = self.table_stats.table_statistic.statistic_dict.get(colname)
        if col_stats_info is None:
            logging.warning(f"Column statistic not found for "
                            f"db_name: {self.table_stats.table_meta.dbname}, "
                            f"table_name: {self.table_stats.table_meta.table_name}, "
                            f"req_json_item {req_json_item}")
            return {}
        ndv_value = self.ndv(None, [colname])
        slots_payload = []
        for slot in (col_stats_info.slots or []):
            if hasattr(slot, "model_dump"):
                slots_payload.append(slot.model_dump(exclude_none=True))
            else:
                slots_payload.append({
                    "kind": getattr(slot, "kind", None),
                    "op": getattr(slot, "op", None),
                    "coll": getattr(slot, "coll", None),
                    "numbers": getattr(slot, "numbers", None),
                    "values": getattr(slot, "values", None),
                })
        res = {
            "stanullfrac": col_stats_info.stanullfrac,
            "stawidth": col_stats_info.stawidth,
            "stainherit": col_stats_info.stainherit,
            "stadistinct": ndv_value,
            "slots": slots_payload,
        }
        logging.info(f"Get pg column statistic for "
                     f"db_name: {self.table_stats.table_meta.dbname}, "
                     f"table_name: {self.table_stats.table_meta.table_name}, "
                     f"column {colname}: {res}")
        return res

    def table_block_relation_estimate_size(self, req_json_item: dict) -> dict:
        table : PGTable = self.table_stats.table_meta
        logging.info(f"Start to get pg table block relation estimate size for "
                     f"db_name: {table.dbname}, "
                     f"table_name: {table.table_name}")
        res = {
            "relpages": table.relpages,
            "reltuples": table.reltuples,
            "relallvisible": table.relallvisible,
            "relhasindex": len(table.indexes) > 0,
        }
        logging.info(f"Get pg table block relation estimate size for "
                     f"db_name: {table.dbname}, "
                     f"table_name: {table.table_name}: {res}")
        return res
    def get_index_stats(self, req_json_item: dict) -> dict:
        return NotImplementedError("get_index_stats is not implemented yet.")