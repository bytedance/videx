-- reset optimizer cost back to MySQL 8.0 default value
SET GLOBAL optimizer_switch='subquery_to_derived=on';
SET GLOBAL optimizer_switch='block_nested_loop=on,hash_join=on';
SET GLOBAL optimizer_switch='semijoin=on';
SET GLOBAL optimizer_switch='firstmatch=on,loosescan=on,duplicateweedout=on';
SET GLOBAL optimizer_switch='materialization=on';

-- reset mysql.server_cost back to MySQL 8.0 default value
UPDATE mysql.server_cost SET cost_value = DEFAULT;
FLUSH OPTIMIZER_COSTS;