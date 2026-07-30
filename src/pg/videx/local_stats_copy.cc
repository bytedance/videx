#include "local_stats_copy.h"

extern void
copy_pg_statistic(Oid src_relid, Oid dst_relid)
{
    Relation stat_rel;
    ScanKeyData key;
    SysScanDesc scan;
    HeapTuple tup;
    CatalogIndexState indstate;
    HeapTuple oldtup;

    Datum values[Natts_pg_statistic];
    bool nulls[Natts_pg_statistic];
    bool replaces[Natts_pg_statistic];

    stat_rel = table_open(StatisticRelationId, RowExclusiveLock);
    if (!RelationIsValid(stat_rel))
        elog(ERROR, "failed to open pg_statistic");


    ScanKeyInit(&key,
                Anum_pg_statistic_starelid,
                BTEqualStrategyNumber,
                F_OIDEQ,
                ObjectIdGetDatum(src_relid));

    scan = systable_beginscan(stat_rel,
                               StatisticRelidAttnumInhIndexId,
                               true, NULL, 1, &key);

    indstate = CatalogOpenIndexes(stat_rel);

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

        heap_deform_tuple(tup, RelationGetDescr(stat_rel), values, nulls);

        values[Anum_pg_statistic_starelid - 1] = ObjectIdGetDatum(dst_relid);
        values[Anum_pg_statistic_staattnum - 1] = Int16GetDatum(dst_attnum);

        oldtup = SearchSysCache3(STATRELATTINH,
                                           ObjectIdGetDatum(dst_relid),
                                           Int16GetDatum(dst_attnum),
                                           BoolGetDatum(stat_form->stainherit));

        if (HeapTupleIsValid(oldtup))
        {
            HeapTuple newtup = heap_modify_tuple(oldtup,
                                                 RelationGetDescr(stat_rel),
                                                 values, nulls, replaces);
            ReleaseSysCache(oldtup);
            CatalogTupleUpdateWithInfo(stat_rel, &newtup->t_self, newtup, indstate);
            heap_freetuple(newtup);
        }
        else
        {
            HeapTuple newtup = heap_form_tuple(RelationGetDescr(stat_rel), values, nulls);
            CatalogTupleInsertWithInfo(stat_rel, newtup, indstate);
            heap_freetuple(newtup);
        }
    }

    CatalogCloseIndexes(indstate);
    systable_endscan(scan);
    table_close(stat_rel, RowExclusiveLock);
}

extern void
copy_pg_statistic_ext(Oid src_relid, Oid dst_relid)
{
    Relation stat_ext_rel;
    ScanKeyData key;
    SysScanDesc scan;
    HeapTuple tup;
    HeapTuple newtup;
    CatalogIndexState indstate;

    stat_ext_rel = table_open(StatisticExtRelationId, RowExclusiveLock);
    if (!RelationIsValid(stat_ext_rel))
        elog(ERROR, "failed to open pg_statistic_ext");

    ScanKeyInit(&key,
                 Anum_pg_statistic_ext_stxrelid,
                 BTEqualStrategyNumber,
                 F_OIDEQ,
                 ObjectIdGetDatum(dst_relid));
    scan = systable_beginscan(stat_ext_rel,
                               StatisticExtRelidIndexId,
                               true, NULL, 1, &key);

    indstate = CatalogOpenIndexes(stat_ext_rel);

    while ((tup = systable_getnext(scan)) != NULL)
    {
        CatalogTupleDelete(stat_ext_rel, &tup->t_self);
    }
    systable_endscan(scan);
    
    ScanKeyInit(&key,
                 Anum_pg_statistic_ext_stxrelid,
                 BTEqualStrategyNumber,
                 F_OIDEQ,
                 ObjectIdGetDatum(src_relid));

    scan = systable_beginscan(stat_ext_rel,
                            StatisticExtRelidIndexId,
                               true, NULL, 1, &key);

    while ((tup = systable_getnext(scan)) != NULL)
    {
        Datum values[Natts_pg_statistic_ext];
        bool nulls[Natts_pg_statistic_ext];
        Oid new_oid;
        Oid namespace_oid;
        char *new_stxname;

        heap_deform_tuple(tup, RelationGetDescr(stat_ext_rel), values, nulls);

        values[Anum_pg_statistic_ext_stxrelid - 1] = ObjectIdGetDatum(dst_relid);
        
        new_oid = GetNewOidWithIndex(stat_ext_rel, StatisticExtOidIndexId, Anum_pg_statistic_ext_oid);
        values[Anum_pg_statistic_ext_oid - 1] = ObjectIdGetDatum(new_oid);

        namespace_oid = get_rel_namespace(dst_relid);
        values[Anum_pg_statistic_ext_stxnamespace - 1] = ObjectIdGetDatum(namespace_oid);

        new_stxname = psprintf("viedex_%s", DatumGetCString(values[Anum_pg_statistic_ext_stxname - 1]));
        values[Anum_pg_statistic_ext_stxname - 1] = CStringGetTextDatum(new_stxname); 

        newtup = heap_form_tuple(RelationGetDescr(stat_ext_rel), values, nulls);
        CatalogTupleInsertWithInfo(stat_ext_rel, newtup, indstate);
        
        heap_freetuple(newtup);
    }

    CatalogCloseIndexes(indstate);
    systable_endscan(scan);
    table_close(stat_ext_rel, RowExclusiveLock);
}

extern void
copy_pg_class_stats(Oid src_relid, Oid dst_relid)
{
    HeapTuple src_tup;
    HeapTuple dst_tup;
    Form_pg_class src_form;
    Relation dst_rel;

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
}
