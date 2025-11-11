-- modify optimizer cost for mysql5.7
SET GLOBAL optimizer_switch='subquery_to_derived=off';
SET GLOBAL optimizer_switch='block_nested_loop=on,hash_join=off';
SET GLOBAL optimizer_switch='semijoin=off';
SET GLOBAL optimizer_switch='firstmatch=off,loosescan=off,duplicateweedout=off';
SET GLOBAL optimizer_switch='materialization=off';


-- modify mysql.server_cost for mysql5.7
UPDATE mysql.server_cost
SET cost_value  = 40.0,
    last_update = NOW(),
    comment     = 'Modified to 2x default value for mysql5.7'
WHERE cost_name = 'disk_temptable_create_cost';

UPDATE mysql.server_cost
SET cost_value  = 1.0,
    last_update = NOW(),
    comment     = 'Modified to 2x default value for mysql5.7'
WHERE cost_name = 'disk_temptable_row_cost';

UPDATE mysql.server_cost
SET cost_value  = 0.1,
    last_update = NOW(),
    comment     = 'Modified to 2x default value for mysql5.7'
WHERE cost_name = 'key_compare_cost';

UPDATE mysql.server_cost
SET cost_value  = 2.0,
    last_update = NOW(),
    comment     = 'Modified to 2x default value for mysql5.7'
WHERE cost_name = 'memory_temptable_create_cost';

UPDATE mysql.server_cost
SET cost_value  = 0.2,
    last_update = NOW(),
    comment     = 'Modified to 2x default value for mysql5.7'
WHERE cost_name = 'memory_temptable_row_cost';

UPDATE mysql.server_cost
SET cost_value  = 0.2,
    last_update = NOW(),
    comment     = 'Modified to 2x default value for mysql5.7'
WHERE cost_name = 'row_evaluate_cost';

FLUSH OPTIMIZER_COSTS;