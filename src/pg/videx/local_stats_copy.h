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
    #include "catalog/pg_index.h"
    #include "catalog/pg_statistic_ext.h"
    #include "catalog/pg_database_d.h"
}

#include <string>

extern void 
copy_pg_statistic(Oid src_relid, Oid dst_relid);

extern void
copy_pg_statistic_ext(Oid src_relid, Oid dst_relid);

extern void
copy_pg_class_stats(Oid src_relid, Oid dst_relid);