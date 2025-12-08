extern "C" {
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
    #include "catalog/pg_index.h"
    #include "catalog/pg_statistic_ext.h"
    #include "utils/selfuncs.h"
    #include "commands/dbcommands.h"
    #include "miscadmin.h"
    #include "utils/guc.h"
    #include "optimizer/pathnode.h"
    #include "parser/parsetree.h"
    #include "parser/parse_clause.h"

    PG_MODULE_MAGIC;
    PG_FUNCTION_INFO_V1(videx_analyze);
    PG_FUNCTION_INFO_V1(videx_tableam_handler);
}
#include "videx_json_item.h"
#include <curl/curl.h>
#include <nlohmann/json.hpp>

static const TableAmRoutine videxam_methods = {
        .type = T_TableAmRoutine,
        .slot_callbacks = videx_slot_callbacks,
        .scan_begin = videx_scan_begin,
        .scan_end = videx_scan_end,
        .scan_rescan = videx_scan_rescan,
        .scan_getnextslot = videx_getnextslot,
        .scan_set_tidrange = NULL,
        .scan_getnextslot_tidrange = NULL,
        .parallelscan_estimate = table_block_parallelscan_estimate,
        .parallelscan_initialize = table_block_parallelscan_initialize,
        .parallelscan_reinitialize = table_block_parallelscan_reinitialize,
        .index_fetch_begin = videx_index_fetch_begin,
        .index_fetch_reset = videx_index_fetch_reset,
        .index_fetch_end = videx_index_fetch_end,
        .index_fetch_tuple = videx_index_fetch_tuple,
        .tuple_fetch_row_version = NULL,
        .tuple_tid_valid = NULL,
        .tuple_get_latest_tid = NULL,
        .tuple_satisfies_snapshot = NULL,
        .index_delete_tuples = NULL,
        .tuple_insert = NULL,
        .tuple_insert_speculative = NULL,
        .tuple_complete_speculative = NULL,
        .multi_insert = NULL,
        .tuple_delete =NULL,
        .tuple_update = NULL,
        .tuple_lock = NULL,
        .finish_bulk_insert = NULL,
        .relation_set_new_filelocator = videx_relation_set_new_filelocator,
        .relation_nontransactional_truncate = NULL,
        .relation_copy_data = NULL,
        .relation_copy_for_cluster = NULL,
        .relation_vacuum = NULL,
        .scan_analyze_next_block = videx_scan_analyze_next_block,
        .scan_analyze_next_tuple = videx_scan_analyze_next_tuple,
        .index_build_range_scan = videx_index_build_range_scan,
        .index_validate_scan = videx_index_validate_scan,
        .relation_size = videx_relation_size,
        .relation_needs_toast_table = videx_relation_needs_toast_table,
        .relation_toast_am = videx_relation_toast_am,
        .relation_fetch_toast_slice = NULL,
        .relation_estimate_size = videx_relation_estimate_size,
        .scan_bitmap_next_block = NULL,
        .scan_bitmap_next_tuple = NULL,
        .scan_sample_next_block = NULL,
        .scan_sample_next_tuple = NULL,
};

static void
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

static void
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

static void
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

Datum
videx_analyze(PG_FUNCTION_ARGS)
{
    Oid src_relid = PG_GETARG_OID(0);
    Oid dst_relid = PG_GETARG_OID(1);

    elog(INFO, "Copying statistic from %u to %u", src_relid, dst_relid);
    copy_pg_class_stats(src_relid, dst_relid);
    copy_pg_statistic(src_relid, dst_relid);
    copy_pg_statistic_ext(src_relid, dst_relid);

    CommandCounterIncrement();
    CacheInvalidateRelcacheByRelid(dst_relid);
    PG_RETURN_VOID();
}

Datum
videx_tableam_handler(PG_FUNCTION_ARGS)
{
	PG_RETURN_POINTER(&videxam_methods);
}

static get_relation_stats_hook_type prev_get_relation_stats_hook = NULL;
static get_index_stats_hook_type  prev_get_index_stats_hook = NULL;


static bool videx_get_relation_stats(PlannerInfo *root,
                                              RangeTblEntry *rte,
                                              AttrNumber attnum,
                                              VariableStatData *vardata);
static bool videx_get_index_stats(PlannerInfo *root,
                                           Oid indexOid,
                                           AttrNumber indexattnum,
                                           VariableStatData *vardata);

/*
 * Module load callback
 */
void
_PG_init(void)
{
	DefineCustomStringVariable("VIDEX_SERVER",
								"set the ip::port for videx statistic server",
								"set the ip::port for videx statistic server",
								&videx_server,
								"127.0.0.1:5001",
								PGC_SUSET,
								0,
								NULL,
								NULL,
								NULL);
    /*Install hooks*/
    prev_get_relation_stats_hook = get_relation_stats_hook;
    get_relation_stats_hook = videx_get_relation_stats;
    prev_get_index_stats_hook = get_index_stats_hook;
    get_index_stats_hook = videx_get_index_stats;
}

static Index
find_rti_by_rte(PlannerInfo *root, RangeTblEntry *rte)
{
    if (!root || !root->simple_rte_array || !rte)
        return 0;
    for (Index i = 1; i <= (Index) root->simple_rel_array_size; i++)
    {
        if (root->simple_rte_array[i] == rte)
            return i;
    }
    return 0;
}

static const int PGSTAT_MAX_SLOTS = 5;

static void
pgstat_apply_slots(VidexStringMap &res_json, Datum *values, bool *nulls)
{
    nlohmann::json slots_json = nlohmann::json::array();

    auto slots_iter = res_json.find("slots");
    if (slots_iter != res_json.end())
    {
        const std::string &raw = slots_iter->second;
        // elog(INFO, "slots: %s", raw.c_str());
        if (!raw.empty())
        {
            nlohmann::json parsed = nlohmann::json::parse(raw, nullptr, false);
            if (parsed.is_discarded() || !parsed.is_array())
            {
                std::string normalized = raw;
                for (char &ch : normalized)
                    if (ch == '\'')
                        ch = '"';

                auto replace_token = [&normalized](const std::string &from, const std::string &to)
                {
                    size_t pos = 0;
                    while ((pos = normalized.find(from, pos)) != std::string::npos)
                    {
                        normalized.replace(pos, from.length(), to);
                        pos += to.length();
                    }
                };

                replace_token("True", "true");
                replace_token("False", "false");
                replace_token("None", "null");

                parsed = nlohmann::json::parse(normalized, nullptr, false);
            }

            if (!parsed.is_discarded() && parsed.is_array())
                slots_json = parsed;
            else
                elog(WARNING,
                     "BuildPGStatisticTuple: invalid slots payload: %s",
                     raw.c_str());
        }
    }

    for (int i = 0; i < PGSTAT_MAX_SLOTS; ++i)
    {
        if (i < static_cast<int>(slots_json.size()) && slots_json[i].is_object())
        {
            const nlohmann::json &slot = slots_json[i];

            bool isnull = false;
            Datum datum = (Datum) 0;
            if (slot.contains("kind") && !slot["kind"].is_null())
            {
                try {
                    datum = Int16GetDatum(slot["kind"].is_string()
                                              ? static_cast<int16>(std::stoi(slot["kind"].get<std::string>()))
                                              : static_cast<int16>(slot["kind"].get<int>()));
                } catch (...) {
                    isnull = true;
                }
            }
            else
                isnull = true;
            values[Anum_pg_statistic_stakind1 - 1 + i] = datum;
            nulls[Anum_pg_statistic_stakind1 - 1 + i] = isnull;

            isnull = false;
            datum = (Datum) 0;
            if (slot.contains("op") && !slot["op"].is_null())
            {
                try {
                    datum = ObjectIdGetDatum(slot["op"].is_string()
                                                 ? static_cast<Oid>(std::stoul(slot["op"].get<std::string>()))
                                                 : static_cast<Oid>(slot["op"].get<long>()));
                } catch (...) {
                    isnull = true;
                }
            }
            else
                isnull = true;
            values[Anum_pg_statistic_staop1 - 1 + i] = datum;
            nulls[Anum_pg_statistic_staop1 - 1 + i] = isnull;

            isnull = false;
            datum = (Datum) 0;
            if (slot.contains("coll") && !slot["coll"].is_null())
            {
                try {
                    datum = ObjectIdGetDatum(slot["coll"].is_string()
                                                 ? static_cast<Oid>(std::stoul(slot["coll"].get<std::string>()))
                                                 : static_cast<Oid>(slot["coll"].get<long>()));
                } catch (...) {
                    isnull = true;
                }
            }
            else
                isnull = true;
            values[Anum_pg_statistic_stacoll1 - 1 + i] = datum;
            nulls[Anum_pg_statistic_stacoll1 - 1 + i] = isnull;

            if (slot.contains("numbers") && slot["numbers"].is_array() && !slot["numbers"].empty())
            {
                std::vector<Datum> elems;
                elems.reserve(slot["numbers"].size());
                for (const auto &item : slot["numbers"])
                {
                    try {
                        float4 val = item.is_string()
                                         ? static_cast<float4>(std::stof(item.get<std::string>()))
                                         : static_cast<float4>(item.get<double>());
                        elems.push_back(Float4GetDatum(val));
                    } catch (...) {
                        /* ignore invalid entry */
                    }
                }

                if (!elems.empty())
                {
                    ArrayType *arr = construct_array(elems.data(),
                                                     elems.size(),
                                                     FLOAT4OID,
                                                     sizeof(float4),
                                                     true,
                                                     'i');
                    values[Anum_pg_statistic_stanumbers1 - 1 + i] = PointerGetDatum(arr);
                    nulls[Anum_pg_statistic_stanumbers1 - 1 + i] = false;
                }
                else
                    nulls[Anum_pg_statistic_stanumbers1 - 1 + i] = true;
            }
            else
                nulls[Anum_pg_statistic_stanumbers1 - 1 + i] = true;

            if (slot.contains("values") && slot["values"].is_array() && !slot["values"].empty())
            {
                std::vector<Datum> elems;
                elems.reserve(slot["values"].size());
                for (const auto &item : slot["values"])
                {
                    std::string text;
                    if (item.is_string())
                        text = item.get<std::string>();
                    else if (item.is_object() && item.contains("value") && item["value"].is_string())
                        text = item["value"].get<std::string>();
                    else
                        text = item.dump();

                    elems.push_back(CStringGetTextDatum(text.c_str()));
                }

                if (!elems.empty())
                {
                    ArrayType *arr = construct_array(elems.data(),
                                                     elems.size(),
                                                     TEXTOID,
                                                     -1,
                                                     false,
                                                     'i');
                    values[Anum_pg_statistic_stavalues1 - 1 + i] = PointerGetDatum(arr);
                    nulls[Anum_pg_statistic_stavalues1 - 1 + i] = false;
                }
                else
                    nulls[Anum_pg_statistic_stavalues1 - 1 + i] = true;
            }
            else
                nulls[Anum_pg_statistic_stavalues1 - 1 + i] = true;
        }
        else
        {
            nulls[Anum_pg_statistic_stakind1 - 1 + i] = true;
            nulls[Anum_pg_statistic_staop1 - 1 + i] = true;
            nulls[Anum_pg_statistic_stacoll1 - 1 + i] = true;
            nulls[Anum_pg_statistic_stanumbers1 - 1 + i] = true;
            nulls[Anum_pg_statistic_stavalues1 - 1 + i] = true;
        }
    }
}

HeapTuple
BuildPGStatisticTuple(VidexStringMap &res_json, Oid relid, int attnum)
{
     if (res_json.empty() ||
        !res_json.count("stainherit") ||
        !res_json.count("stanullfrac") ||
        !res_json.count("stawidth") ||
        !res_json.count("stadistinct"))
    {
        return NULL;
    }
    Datum values[Natts_pg_statistic];
    bool nulls[Natts_pg_statistic];
    MemSet(nulls, 0, sizeof(nulls));

    values[Anum_pg_statistic_starelid - 1] = ObjectIdGetDatum(relid);
    values[Anum_pg_statistic_staattnum - 1] = Int16GetDatum(attnum);
        const std::string &stainherit_str = res_json.at("stainherit");
    bool stainherit = (stainherit_str == "true" || stainherit_str == "True" || stainherit_str == "1");
    values[Anum_pg_statistic_stainherit - 1] = BoolGetDatum(stainherit);

    float4 stanullfrac = 0.0f;
    try { stanullfrac = static_cast<float4>(std::stof(res_json.at("stanullfrac"))); }
    catch (...) { ereport(WARNING, (errmsg("invalid stanullfrac: %s", res_json.at("stanullfrac").c_str()))); }
    values[Anum_pg_statistic_stanullfrac - 1] = Float4GetDatum(stanullfrac);

    int32 stawidth = 0;
    try { stawidth = static_cast<int32>(std::stol(res_json.at("stawidth"))); }
    catch (...) { ereport(WARNING, (errmsg("invalid stawidth: %s", res_json.at("stawidth").c_str()))); }
    values[Anum_pg_statistic_stawidth - 1] = Int32GetDatum(stawidth);

    float4 stadistinct = -1.0f;
    try { stadistinct = static_cast<float4>(std::stof(res_json.at("stadistinct"))); }
    catch (...) { ereport(WARNING, (errmsg("invalid stadistinct: %s", res_json.at("stadistinct").c_str()))); }
    values[Anum_pg_statistic_stadistinct - 1] = Float4GetDatum(stadistinct);

    // elog(INFO, "stainherit=%s stanullfrac=%f stawidth=%d stadistinct=%f",
    //      stainherit ? "true" : "false", stanullfrac, stawidth, stadistinct);
    pgstat_apply_slots(res_json, values, nulls);

    Relation stat_rel = table_open(StatisticRelationId, AccessShareLock);
    HeapTuple tuple = heap_form_tuple(RelationGetDescr(stat_rel), values, nulls);
    table_close(stat_rel, AccessShareLock);

    return tuple;
}

static bool videx_get_relation_stats(PlannerInfo *root,
                                              RangeTblEntry *rte,
                                              AttrNumber attnum,
                                              VariableStatData *vardata){
    Oid nspoid = get_rel_namespace(rte->relid);
    if (IsCatalogNamespace(nspoid) || IsToastNamespace(nspoid)) {
        if (prev_get_relation_stats_hook)
            return prev_get_relation_stats_hook(root, rte, attnum, vardata);
        else
            return false;
    }
    if (rte->rtekind == RTE_RELATION){
        /*fetch HeapTuple of pg_statistic from videx_statistic_server*/
        char *dbname = get_database_name(MyDatabaseId);
        char *relname   = get_rel_name(rte->relid);
        char *nspname   = get_namespace_name(get_rel_namespace(rte->relid));
        char *colname = get_attname(rte->relid, attnum, false);
        /*To adapt with videx-statistic-server, we use schema_name.table_name to instead of table_name*/
        std::string ns_relname = std::string(nspname) + "." + std::string(relname);

        VidexStringMap res_json;
        VidexJsonItem request_item = construct_request(dbname,nspname,ns_relname.c_str(),__PRETTY_FUNCTION__);
        VidexJsonItem * keyItem = request_item.create("colname");
        keyItem->add_property("name", colname);

        int error = ask_from_videx_http(request_item, res_json);
        if (error) {
            std::cout << "ask_from_videx_http error. videx_get_realtion_stats" << std::endl;
            return prev_get_relation_stats_hook ?
                   prev_get_relation_stats_hook(root, rte, attnum, vardata) :
                   false;
        }
        vardata->statsTuple = BuildPGStatisticTuple(res_json,rte->relid,attnum);
        vardata->freefunc = heap_freetuple;
        /**
         * TODO: 
         * 1. may be we can also update local cache of pg_statistic here 
         * 2. we need more stawidth in pg_statistic for select list to calucate width in query plan
         * */
        if (HeapTupleIsValid(vardata->statsTuple)) {
            vardata->acl_ok = true;
        }
    } else if ((rte->rtekind == RTE_SUBQUERY && !rte->inh) ||
			 (rte->rtekind == RTE_CTE && !rte->self_reference)){
        PlannerInfo *subroot;
		Query	   *subquery;
		List	   *subtlist;
		TargetEntry *ste;

        if (rte->rtekind == RTE_SUBQUERY) {
            RelOptInfo *rel;
            Index rti = find_rti_by_rte(root, rte);
            rel = find_base_rel(root, rti);
			subroot = rel->subroot;
        } else {
            PlannerInfo *cteroot;
			Index		levelsup;
			int			ndx;
			int			plan_id;
			ListCell   *lc;

            levelsup = rte->ctelevelsup;
			cteroot = root;
			while (levelsup-- > 0)
			{
				cteroot = cteroot->parent_root;
				if (!cteroot)	/* shouldn't happen */
					elog(ERROR, "bad levelsup for CTE \"%s\"", rte->ctename);
			}
            ndx = 0;
			foreach(lc, cteroot->parse->cteList)
			{
				CommonTableExpr *cte = (CommonTableExpr *) lfirst(lc);

				if (strcmp(cte->ctename, rte->ctename) == 0)
					break;
				ndx++;
			}
			if (lc == NULL)		/* shouldn't happen */
				elog(ERROR, "could not find CTE \"%s\"", rte->ctename);
			if (ndx >= list_length(cteroot->cte_plan_ids))
				elog(ERROR, "could not find plan for CTE \"%s\"", rte->ctename);
			plan_id = list_nth_int(cteroot->cte_plan_ids, ndx);
			if (plan_id <= 0)
				elog(ERROR, "no plan was made for CTE \"%s\"", rte->ctename);
			subroot = (PlannerInfo *) list_nth(root->glob->subroots, plan_id - 1);
        }
        /* If the subquery hasn't been planned yet, we have to punt */
		if (subroot == NULL)
			return true;
		Assert(IsA(subroot, PlannerInfo));
        subquery = subroot->parse;
		Assert(IsA(subquery, Query));
        if (subquery->setOperations ||
			subquery->groupClause ||
			subquery->groupingSets)
			return true;
        /* Get the subquery output expression referenced by the upper Var */
		if (subquery->returningList)
			subtlist = subquery->returningList;
		else
			subtlist = subquery->targetList;
        Index rti = find_rti_by_rte(root, rte);
		ste = get_tle_by_resno(subtlist, rti);
		if (ste == NULL || ste->resjunk)
			elog(ERROR, "subquery %s does not have attribute %d",
				 rte->eref->aliasname, rti);
		Var* var = (Var *) ste->expr;
        if (subquery->distinctClause)
		{
			if (list_length(subquery->distinctClause) == 1 &&
				targetIsInSortList(ste, InvalidOid, subquery->distinctClause))
				vardata->isunique = true;
			/* cannot go further */
			return true;
		}
        if (rte->security_barrier)
			return true;
        /* Can only handle a simple Var of subquery's query level */
		if (var && IsA(var, Var) &&
			var->varlevelsup == 0)
		{
			RangeTblEntry *sub_rte = subroot->simple_rte_array[var->varno];
            if (!sub_rte || sub_rte->rtekind != RTE_RELATION)
                return true;
            return videx_get_relation_stats(subroot, sub_rte, var->varattno, vardata);
        }
    }
    return true;
}

static bool videx_get_index_stats(PlannerInfo *root,
                                           Oid indexOid,
                                           AttrNumber indexattnum,
                                           VariableStatData *vardata){
    return prev_get_index_stats_hook ?
           prev_get_index_stats_hook(root, indexOid, indexattnum, vardata) :
           false;
}

