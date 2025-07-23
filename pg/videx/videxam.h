#ifndef VIDEXAM_H
#define VIDEXAM_H

#include "access/relation.h"	/* for backward compatibility */
#include "access/relscan.h"
#include "access/sdir.h"
#include "access/skey.h"
#include "access/table.h"		/* for backward compatibility */
#include "access/tableam.h"
#include "nodes/lockoptions.h"
#include "nodes/primnodes.h"
#include "storage/bufpage.h"
#include "storage/dsm.h"
#include "storage/lockdefs.h"
#include "storage/read_stream.h"
#include "storage/shm_toc.h"
#include "utils/relcache.h"
#include "utils/snapshot.h"


struct VidexScanDesc {
  /*Base class from access/relscan.h.*/
  TableScanDescData rs_base;
  uint32 cursor;
};


extern const TupleTableSlotOps* videx_slot_callbacks(Relation rel);
extern void videx_relation_estimate_size(Relation rel, int32 *attr_widths, 
        BlockNumber *pages, double *tuples, double *allvisfrac);
extern uint64 videx_relation_size(Relation rel, ForkNumber forkNumber);
extern TableScanDesc videx_scan_begin(Relation rel, Snapshot snapshot,
     int nkeys, struct ScanKeyData *key, ParallelTableScanDesc pscan, uint32 flags);
extern void videx_scan_end (TableScanDesc scan);
extern void videx_scan_rescan (TableScanDesc scan, struct ScanKeyData *key, 
    bool set_params, bool allow_strat, bool allow_sync, bool allow_pagemode);
extern bool videx_getnextslot (TableScanDesc scan, ScanDirection direction,
     TupleTableSlot *slot);
extern void videx_relation_set_new_filelocator (Relation rel,
												 const RelFileLocator *newrlocator,
												 char persistence,
												 TransactionId *freezeXid,
												 MultiXactId *minmulti);
extern bool videx_relation_needs_toast_table(Relation rel);
extern Oid videx_relation_toast_am(Relation rel);
extern double videx_index_build_range_scan(Relation table_rel, Relation index_rel, 
     struct IndexInfo *index_info, bool allow_sync, bool anyvisible, bool progress, 
     BlockNumber start_blockno, BlockNumber numblocks, IndexBuildCallback callback, 
     void *callback_state, TableScanDesc scan);
extern void videx_index_validate_scan(Relation table_rel, Relation index_rel, 
     struct IndexInfo *index_info, Snapshot snapshot, struct ValidateIndexState *state);
extern bool videx_scan_analyze_next_block(TableScanDesc scan, ReadStream *stream);
extern bool videx_scan_analyze_next_tuple(TableScanDesc scan, TransactionId OldestXmin, 
     double *liverows, double *deadrows, TupleTableSlot *slot);
// extern Size videx_parallelscan_estimate(Relation rel);
// extern Size videx_parallelscan_initialize(Relation rel, ParallelTableScanDesc pscan);
// extern void videx_parallelscan_reinitialize(Relation rel, ParallelTableScanDesc pscan);
extern struct IndexFetchTableData* videx_index_fetch_begin(Relation rel);
extern void videx_index_fetch_reset(struct IndexFetchTableData *data);
extern void videx_index_fetch_end(struct IndexFetchTableData *data);
extern bool videx_index_fetch_tuple(struct IndexFetchTableData *scan, ItemPointer tid, 
     Snapshot snapshot, TupleTableSlot *slot, bool *call_again, bool *all_dead);
#endif							/* VIDEXAM_H */