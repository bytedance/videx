#include "postgres.h"
#include "access/bufmask.h"
#include "access/heapam_xlog.h"
#include "access/heaptoast.h"
#include "access/hio.h"
#include "access/multixact.h"
#include "access/parallel.h"
#include "access/relscan.h"
#include "access/subtrans.h"
#include "access/syncscan.h"
#include "access/sysattr.h"
#include "access/tableam.h"
#include "access/transam.h"
#include "access/valid.h"
#include "access/visibilitymap.h"
#include "access/xact.h"
#include "access/xlog.h"
#include "access/xloginsert.h"
#include "access/xlogutils.h"
#include "catalog/catalog.h"
#include "catalog/pg_database.h"
#include "catalog/pg_database_d.h"
#include "commands/vacuum.h"
#include "miscadmin.h"
#include "pgstat.h"
#include "port/atomics.h"
#include "port/pg_bitutils.h"
#include "storage/bufmgr.h"
#include "storage/freespace.h"
#include "storage/lmgr.h"
#include "storage/predicate.h"
#include "storage/procarray.h"
#include "storage/standby.h"
#include "utils/datum.h"
#include "utils/injection_point.h"
#include "utils/inval.h"
#include "utils/relcache.h"
#include "utils/snapmgr.h"
#include "utils/spccache.h"
#include "utils/syscache.h"
#include "optimizer/optimizer.h"
#include "optimizer/plancat.h"
#include "videxam.h"
#include <math.h>

#define HEAP_OVERHEAD_BYTES_PER_TUPLE \
	(MAXALIGN(SizeofHeapTupleHeader) + sizeof(ItemIdData))
#define HEAP_USABLE_BYTES_PER_PAGE \
	(BLCKSZ - SizeOfPageHeaderData)

static void
videx_table_block_relation_estimate_size(Relation rel, int32 *attr_widths,
								   BlockNumber *pages, double *tuples,
								   double *allvisfrac,
								   Size overhead_bytes_per_tuple,
						   Size usable_bytes_per_page);

const TupleTableSlotOps *videx_slot_callbacks(Relation rel){
    return &TTSOpsVirtual;
}

void videx_relation_estimate_size(Relation rel, int32 *attr_widths, 
        BlockNumber *pages, double *tuples, double *allvisfrac){
    return videx_table_block_relation_estimate_size(rel, attr_widths, pages,
									   tuples, allvisfrac,
									   HEAP_OVERHEAD_BYTES_PER_TUPLE,
									   HEAP_USABLE_BYTES_PER_PAGE);
}
uint64 videx_relation_size(Relation rel, ForkNumber forkNumber){
    return 0;
}
TableScanDesc videx_scan_begin(Relation rel, Snapshot snapshot,
     int nkeys, struct ScanKeyData *key, ParallelTableScanDesc pscan, uint32 flags){
  struct VidexScanDesc* scan;
  scan = (struct VidexScanDesc*)malloc(sizeof(struct VidexScanDesc));
  scan->rs_base.rs_rd = rel;
  scan->rs_base.rs_snapshot = snapshot;
  scan->rs_base.rs_nkeys = nkeys;
  scan->rs_base.rs_flags = flags;
  scan->rs_base.rs_parallel = pscan;
  scan->cursor = 0;
  return (TableScanDesc)scan;       
}
void videx_scan_end (TableScanDesc scan){
	free(scan);
}
void videx_scan_rescan (TableScanDesc scan, struct ScanKeyData *key, 
    bool set_params, bool allow_strat, bool allow_sync, bool allow_pagemode){}

bool videx_getnextslot (TableScanDesc scan, ScanDirection direction,
     TupleTableSlot *slot){
	// struct VidexScanDesc* vscan = NULL;
	// vscan = (struct VidexScanDesc*) scan;
  	ExecClearTuple(slot);
	return false;
}

void
videx_table_block_relation_estimate_size(Relation rel, int32 *attr_widths,
								   BlockNumber *pages, double *tuples,
								   double *allvisfrac,
								   Size overhead_bytes_per_tuple,
								   Size usable_bytes_per_page)
{
	BlockNumber curpages;
	BlockNumber relpages;
	double		reltuples;
	BlockNumber relallvisible;
	double		density;

	/* skip videx_relation_size , let curpage equal to relpages directly */
	curpages = (BlockNumber) rel->rd_rel->relpages;

	/* coerce values in pg_class to more desirable types */
	relpages = (BlockNumber) rel->rd_rel->relpages;
	reltuples = (double) rel->rd_rel->reltuples;
	relallvisible = (BlockNumber) rel->rd_rel->relallvisible;

	/*
	 * HACK: if the relation has never yet been vacuumed, use a minimum size
	 * estimate of 10 pages.  The idea here is to avoid assuming a
	 * newly-created table is really small, even if it currently is, because
	 * that may not be true once some data gets loaded into it.  Once a vacuum
	 * or analyze cycle has been done on it, it's more reasonable to believe
	 * the size is somewhat stable.
	 *
	 * (Note that this is only an issue if the plan gets cached and used again
	 * after the table has been filled.  What we're trying to avoid is using a
	 * nestloop-type plan on a table that has grown substantially since the
	 * plan was made.  Normally, autovacuum/autoanalyze will occur once enough
	 * inserts have happened and cause cached-plan invalidation; but that
	 * doesn't happen instantaneously, and it won't happen at all for cases
	 * such as temporary tables.)
	 *
	 * We test "never vacuumed" by seeing whether reltuples < 0.
	 *
	 * If the table has inheritance children, we don't apply this heuristic.
	 * Totally empty parent tables are quite common, so we should be willing
	 * to believe that they are empty.
	 */
	if (curpages < 10 &&
		reltuples < 0 &&
		!rel->rd_rel->relhassubclass)
		curpages = 10;

	/* report estimated # pages */
	*pages = curpages;
	/* quick exit if rel is clearly empty */
	if (curpages == 0)
	{
		*tuples = 0;
		*allvisfrac = 0;
		return;
	}

	/* estimate number of tuples from previous tuple density */
	if (reltuples >= 0 && relpages > 0)
		density = reltuples / (double) relpages;
	else
	{
		/*
		 * When we have no data because the relation was never yet vacuumed,
		 * estimate tuple width from attribute datatypes.  We assume here that
		 * the pages are completely full, which is OK for tables but is
		 * probably an overestimate for indexes.  Fortunately
		 * get_relation_info() can clamp the overestimate to the parent
		 * table's size.
		 *
		 * Note: this code intentionally disregards alignment considerations,
		 * because (a) that would be gilding the lily considering how crude
		 * the estimate is, (b) it creates platform dependencies in the
		 * default plans which are kind of a headache for regression testing,
		 * and (c) different table AMs might use different padding schemes.
		 */
		int32		tuple_width;
		int			fillfactor;

		/*
		 * Without reltuples/relpages, we also need to consider fillfactor.
		 * The other branch considers it implicitly by calculating density
		 * from actual relpages/reltuples statistics.
		 */
		fillfactor = RelationGetFillFactor(rel, HEAP_DEFAULT_FILLFACTOR);

		tuple_width = get_rel_data_width(rel, attr_widths);
		tuple_width += overhead_bytes_per_tuple;
		/* note: integer division is intentional here */
		density = (usable_bytes_per_page * fillfactor / 100) / tuple_width;
		/* There's at least one row on the page, even with low fillfactor. */
		density = clamp_row_est(density);
	}
	*tuples = rint(density * (double) curpages);

	/*
	 * We use relallvisible as-is, rather than scaling it up like we do for
	 * the pages and tuples counts, on the theory that any pages added since
	 * the last VACUUM are most likely not marked all-visible.  But costsize.c
	 * wants it converted to a fraction.
	 */
	if (relallvisible == 0 || curpages <= 0)
		*allvisfrac = 0;
	else if ((double) relallvisible >= curpages)
		*allvisfrac = 1;
	else
		*allvisfrac = (double) relallvisible / curpages;
}

void videx_relation_set_new_filelocator (Relation rel,
												 const RelFileLocator *newrlocator,
												 char persistence,
												 TransactionId *freezeXid,
												 MultiXactId *minmulti){			
	return;									
}

bool videx_relation_needs_toast_table(Relation rel){
	return false;
}

Oid videx_relation_toast_am(Relation rel){
  Oid oid = 0;
  return oid;
}
double videx_index_build_range_scan(Relation table_rel, Relation index_rel, 
     struct IndexInfo *index_info, bool allow_sync, bool anyvisible, bool progress, 
     BlockNumber start_blockno, BlockNumber numblocks, IndexBuildCallback callback, 
     void *callback_state, TableScanDesc scan){
	return 0;
}
void videx_index_validate_scan(Relation table_rel, Relation index_rel, 
     struct IndexInfo *index_info, Snapshot snapshot, struct ValidateIndexState *state){
	return;
}

bool videx_scan_analyze_next_block(TableScanDesc scan, ReadStream *stream){
	return false;
}

bool videx_scan_analyze_next_tuple(TableScanDesc scan, TransactionId OldestXmin, 
     double *liverows, double *deadrows, TupleTableSlot *slot){
	return false;
}

// Size videx_parallelscan_estimate(Relation rel){

// }

// Size videx_parallelscan_initialize(Relation rel, ParallelTableScanDesc pscan){

// }

// void videx_parallelscan_reinitialize(Relation rel, ParallelTableScanDesc pscan){

// }

struct IndexFetchTableData* videx_index_fetch_begin(Relation rel){
	return NULL;
}
void videx_index_fetch_reset(struct IndexFetchTableData *data){
	
}
void videx_index_fetch_end(struct IndexFetchTableData *data){

}
bool videx_index_fetch_tuple(struct IndexFetchTableData *scan, ItemPointer tid, 
     Snapshot snapshot, TupleTableSlot *slot, bool *call_again, bool *all_dead){
	return false;
}
