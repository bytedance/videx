#include "postgres.h"
#include "fmgr.h"
#include "utils/fmgroids.h"
#include "access/htup_details.h"
#include "catalog/pg_statistic.h"
#include "catalog/pg_class.h"
#include "catalog/pg_namespace.h"
#include "utils/rel.h"
#include "utils/syscache.h"
#include "utils/lsyscache.h"
#include "utils/builtins.h"
#include "catalog/indexing.h"
#include "access/table.h"
#include "access/tableam.h"
#include "utils/relcache.h"
#include "utils/inval.h"
#include "access/multixact.h"
#include "commands/vacuum.h"
#include "videxam.h"
#include "access/heapam.h"

PG_MODULE_MAGIC;
PG_FUNCTION_INFO_V1(videx_analyze);
PG_FUNCTION_INFO_V1(videx_tableam_handler);

static void
copy_pg_statistic(Oid src_relid, Oid dst_relid)
{
    Relation statRel;
    ScanKeyData key;
    SysScanDesc scan;
    HeapTuple tup;
    CatalogIndexState indstate;
    HeapTuple oldtup;

    Datum values[Natts_pg_statistic];
    bool nulls[Natts_pg_statistic];
    bool replaces[Natts_pg_statistic];

    statRel = table_open(StatisticRelationId, RowExclusiveLock);
    if (!RelationIsValid(statRel))
        elog(ERROR, "failed to open pg_statistic");

    ScanKeyInit(&key,
                Anum_pg_statistic_starelid,
                BTEqualStrategyNumber,
                F_OIDEQ,
                ObjectIdGetDatum(src_relid));

    scan = systable_beginscan(statRel,
                               StatisticRelidAttnumInhIndexId,
                               true, NULL, 1, &key);

    indstate = CatalogOpenIndexes(statRel);

    while ((tup = systable_getnext(scan)) != NULL)
    {
        Form_pg_statistic stat_form = (Form_pg_statistic) GETSTRUCT(tup);

        char *colname = get_attname(src_relid, stat_form->staattnum, false);
        AttrNumber dst_attnum = get_attnum(dst_relid, colname);

        if (dst_attnum == InvalidAttrNumber)
            ereport(ERROR,
                    (errmsg("target table does not contain column \"%s\"", colname)));


        memset(values, 0, sizeof(values));
        memset(nulls, false, sizeof(nulls));
        memset(replaces, true, sizeof(replaces));

        heap_deform_tuple(tup, RelationGetDescr(statRel), values, nulls);

        values[Anum_pg_statistic_starelid - 1] = ObjectIdGetDatum(dst_relid);
        values[Anum_pg_statistic_staattnum - 1] = Int16GetDatum(dst_attnum);

        oldtup = SearchSysCache3(STATRELATTINH,
                                           ObjectIdGetDatum(dst_relid),
                                           Int16GetDatum(dst_attnum),
                                           BoolGetDatum(stat_form->stainherit));

        if (HeapTupleIsValid(oldtup))
        {
            HeapTuple newtup = heap_modify_tuple(oldtup,
                                                 RelationGetDescr(statRel),
                                                 values, nulls, replaces);
            ReleaseSysCache(oldtup);
            CatalogTupleUpdateWithInfo(statRel, &newtup->t_self, newtup, indstate);
            heap_freetuple(newtup);
        }
        else
        {
            HeapTuple newtup = heap_form_tuple(RelationGetDescr(statRel), values, nulls);
            CatalogTupleInsertWithInfo(statRel, newtup, indstate);
            heap_freetuple(newtup);
        }
    }

    CatalogCloseIndexes(indstate);
    systable_endscan(scan);
    table_close(statRel, RowExclusiveLock);
}


static void
copy_pg_class_stats(Oid src_relid, Oid dst_relid)
{
    Relation rel_rel;
    HeapTuple src_tup;
    HeapTuple dst_tup;
    Form_pg_class src_form;
    Relation dst_rel;

    rel_rel = table_open(RelationRelationId, RowExclusiveLock);
    if (!RelationIsValid(rel_rel))
        elog(ERROR, "failed to open pg_class relation");

    src_tup = SearchSysCache1(RELOID, ObjectIdGetDatum(src_relid));
    dst_tup = SearchSysCache1(RELOID, ObjectIdGetDatum(dst_relid));

    if (!HeapTupleIsValid(src_tup) || !HeapTupleIsValid(dst_tup))
        elog(ERROR, "pg_class tuple not found");

    src_form = (Form_pg_class) GETSTRUCT(src_tup);

    dst_rel = table_open(dst_relid, AccessShareLock);
    
    vac_update_relstats(dst_rel,
                        src_form->relpages,
                        src_form->reltuples,
                        src_form->relallvisible,
                        src_form->relhasindex,
                        InvalidTransactionId,
                        InvalidMultiXactId, 
                        NULL,  
                        NULL,  
                        false 
    );

    table_close(dst_rel, AccessShareLock);

    ReleaseSysCache(src_tup);
    ReleaseSysCache(dst_tup);
    table_close(rel_rel, RowExclusiveLock);
}

Datum
videx_analyze(PG_FUNCTION_ARGS)
{
    Oid src_relid = PG_GETARG_OID(0);
    Oid dst_relid = PG_GETARG_OID(1);

    elog(INFO, "Copying pg_class stats from %u to %u", src_relid, dst_relid);
    copy_pg_class_stats(src_relid, dst_relid);

    elog(INFO, "Copying pg_statistic from %u to %u", src_relid, dst_relid);
    copy_pg_statistic(src_relid, dst_relid);

    CommandCounterIncrement();
    CacheInvalidateRelcacheByRelid(dst_relid);
    PG_RETURN_VOID();
}

static const TableAmRoutine videxam_methods = {
	.type = T_TableAmRoutine,

    .slot_callbacks = videx_slot_callbacks,
    .relation_estimate_size = videx_relation_estimate_size,
    .relation_size = videx_relation_size,

    .scan_begin = videx_scan_begin,
    .scan_end = videx_scan_end,
    .scan_rescan = videx_scan_rescan,

    .scan_getnextslot = videx_getnextslot,
    .relation_set_new_filelocator = videx_relation_set_new_filelocator,

    .relation_needs_toast_table = videx_relation_needs_toast_table,
    .relation_toast_am = videx_relation_toast_am,

    /*for primary key and index*/
    .index_build_range_scan = videx_index_build_range_scan,
    .index_validate_scan = videx_index_validate_scan,
    .scan_analyze_next_block = videx_scan_analyze_next_block,
    .scan_analyze_next_tuple = videx_scan_analyze_next_tuple,

    .parallelscan_estimate = table_block_parallelscan_estimate,
    .parallelscan_initialize = table_block_parallelscan_initialize,
    .parallelscan_reinitialize = table_block_parallelscan_reinitialize,

    .index_fetch_begin = videx_index_fetch_begin,
    .index_fetch_reset = videx_index_fetch_reset,
    .index_fetch_end = videx_index_fetch_end,
    .index_fetch_tuple = videx_index_fetch_tuple,
};

Datum
videx_tableam_handler(PG_FUNCTION_ARGS)
{
	PG_RETURN_POINTER(&videxam_methods);
}

// static get_relation_stats_hook_type prev_get_relation_stats_hook = NULL;
// static get_index_stats_hook_type  prev_get_index_stats_hook = NULL;


// static bool videx_get_relation_stats(PlannerInfo *root,
//                                               RangeTblEntry *rte,
//                                               AttrNumber attnum,
//                                               VariableStatData *vardata);
// static bool videx_get_index_stats(PlannerInfo *root,
//                                            Oid indexOid,
//                                            AttrNumber indexattnum,
//                                            VariableStatData *vardata);


/*
 * Module load callback
 */
// void
// _PG_init(void)
// {
//     /*Install hooks*/
//     // prev_get_relation_stats_hook = get_relation_stats_hook;
//     // get_relation_stats_hook = videx_get_relation_stats;
//     // prev_get_index_stats_hook = get_index_stats_hook;
//     // get_index_stats_hook = videx_get_index_stats;
// }

// static bool videx_get_relation_stats(PlannerInfo *root,
//                                               RangeTblEntry *rte,
//                                               AttrNumber attnum,
//                                               VariableStatData *vardata){
    
// }

// static bool videx_get_index_stats(PlannerInfo *root,
//                                            Oid indexOid,
//                                            AttrNumber indexattnum,
//                                            VariableStatData *vardata){
// }

