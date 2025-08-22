#!/usr/bin/env bash
set -euo pipefail

# === MySQL Connection Info ===
HOST="127.0.0.1"
PORT="13308"
USER="videx"
PASS="password"
DB="tpch_tiny"

# === Output Directory ===
OUTDIR="./outputs"
mkdir -p "$OUTDIR"

# --- Q01 ~ Q21/22/22_simple Definition (All inline, safe heredoc) ---
Q01=$(cat <<'SQL'
SELECT l_returnflag, l_linestatus, sum(l_quantity) AS sum_qty , sum(l_extendedprice) AS sum_base_price , sum(l_extendedprice * (1 - l_discount)) AS sum_disc_price , sum(l_extendedprice * (1 - l_discount) * (1 + l_tax)) AS sum_charge , avg(l_quantity) AS avg_qty, avg(l_extendedprice) AS avg_price , avg(l_discount) AS avg_disc, count(*) AS count_order
FROM lineitem
WHERE l_shipdate <= DATE_SUB(STR_TO_DATE('1998-12-01', '%Y-%m-%d'), INTERVAL 74 DAY)
GROUP BY l_returnflag, l_linestatus
ORDER BY l_returnflag, l_linestatus;
SQL
)

Q02=$(cat <<'SQL'
SELECT s_acctbal, s_name, n_name, p_partkey, p_mfgr , s_address, s_phone, s_comment
FROM part, supplier, partsupp, nation, region
WHERE p_partkey = ps_partkey
  AND s_suppkey = ps_suppkey
  AND p_size = 24
  AND p_type LIKE '%STEEL'
  AND s_nationkey = n_nationkey
  AND n_regionkey = r_regionkey
  AND r_name = 'AMERICA'
  AND ps_supplycost = (
      SELECT min(ps_supplycost)
      FROM partsupp, supplier, nation, region
      WHERE p_partkey = ps_partkey
        AND s_suppkey = ps_suppkey
        AND s_nationkey = n_nationkey
        AND n_regionkey = r_regionkey
        AND r_name = 'AMERICA'
  )
ORDER BY s_acctbal DESC, n_name, s_name, p_partkey;
SQL
)

Q03=$(cat <<'SQL'
SELECT l_orderkey, sum(l_extendedprice * (1 - l_discount)) AS revenue , o_orderdate, o_shippriority
FROM customer, orders, lineitem
WHERE c_mktsegment = 'BUILDING'
  AND c_custkey = o_custkey
  AND l_orderkey = o_orderkey
  AND o_orderdate < STR_TO_DATE('1995-03-08', '%Y-%m-%d')
  AND l_shipdate > STR_TO_DATE('1995-03-08', '%Y-%m-%d')
GROUP BY l_orderkey, o_orderdate, o_shippriority
ORDER BY revenue DESC, o_orderdate;
SQL
)

Q04=$(cat <<'SQL'
SELECT o_orderpriority, count(*) AS order_count
FROM orders
WHERE o_orderdate >= STR_TO_DATE('1994-02-01', '%Y-%m-%d')
  AND o_orderdate < DATE_ADD(STR_TO_DATE('1994-02-01', '%Y-%m-%d'), INTERVAL 3 MONTH)
  AND EXISTS (
    SELECT * FROM lineitem
    WHERE l_orderkey = o_orderkey
      AND l_commitdate < l_receiptdate
  )
GROUP BY o_orderpriority
ORDER BY o_orderpriority;
SQL
)

Q05=$(cat <<'SQL'
SELECT n_name, sum(l_extendedprice * (1 - l_discount)) AS revenue
FROM customer, orders, lineitem, supplier, nation, region
WHERE c_custkey = o_custkey
  AND l_orderkey = o_orderkey
  AND l_suppkey = s_suppkey
  AND c_nationkey = s_nationkey
  AND s_nationkey = n_nationkey
  AND n_regionkey = r_regionkey
  AND r_name = 'EUROPE'
  AND o_orderdate >= STR_TO_DATE('1994-01-01', '%Y-%m-%d')
  AND o_orderdate < DATE_ADD(STR_TO_DATE('1994-01-01', '%Y-%m-%d'), INTERVAL 1 YEAR)
GROUP BY n_name
ORDER BY revenue DESC;
SQL
)

Q06=$(cat <<'SQL'
SELECT sum(l_extendedprice * l_discount) AS revenue
FROM lineitem
WHERE l_shipdate >= STR_TO_DATE('1994-01-01', '%Y-%m-%d')
  AND l_shipdate < DATE_ADD(STR_TO_DATE('1994-01-01', '%Y-%m-%d'), INTERVAL 1 YEAR)
  AND l_discount BETWEEN 0.05 - 0.01 AND 0.05 + 0.01
  AND l_quantity < 24;
SQL
)

Q07=$(cat <<'SQL'
SELECT supp_nation, cust_nation, l_year, sum(volume) AS revenue
FROM (
  SELECT n1.n_name AS supp_nation, n2.n_name AS cust_nation,
         EXTRACT(YEAR FROM l_shipdate) AS l_year,
         l_extendedprice * (1 - l_discount) AS volume
  FROM supplier, lineitem, orders, customer, nation n1, nation n2
  WHERE s_suppkey = l_suppkey
    AND o_orderkey = l_orderkey
    AND c_custkey = o_custkey
    AND s_nationkey = n1.n_nationkey
    AND c_nationkey = n2.n_nationkey
    AND ((n1.n_name = 'IRAN' AND n2.n_name = 'CANADA')
      OR (n1.n_name = 'CANADA' AND n2.n_name = 'IRAN'))
    AND l_shipdate BETWEEN STR_TO_DATE('1995-01-01', '%Y-%m-%d')
                        AND STR_TO_DATE('1996-12-31', '%Y-%m-%d')
) shipping
GROUP BY supp_nation, cust_nation, l_year
ORDER BY supp_nation, cust_nation, l_year;
SQL
)

Q08=$(cat <<'SQL'
SELECT o_year,
       sum(CASE WHEN nation = 'CANADA' THEN volume ELSE 0 END) / sum(volume) AS mkt_share
FROM (
  SELECT EXTRACT(YEAR FROM o_orderdate) AS o_year,
         l_extendedprice * (1 - l_discount) AS volume,
         n2.n_name AS nation
  FROM part, supplier, lineitem, orders, customer, nation n1, nation n2, region
  WHERE p_partkey = l_partkey
    AND s_suppkey = l_suppkey
    AND l_orderkey = o_orderkey
    AND o_custkey = c_custkey
    AND c_nationkey = n1.n_nationkey
    AND n1.n_regionkey = r_regionkey
    AND r_name = 'AMERICA'
    AND s_nationkey = n2.n_nationkey
    AND o_orderdate BETWEEN STR_TO_DATE('1995-01-01', '%Y-%m-%d')
                        AND STR_TO_DATE('1996-12-31', '%Y-%m-%d')
    AND p_type = 'LARGE BURNISHED TIN'
) all_nations
GROUP BY o_year
ORDER BY o_year;
SQL
)

Q09=$(cat <<'SQL'
SELECT nation, o_year, sum(amount) AS sum_profit
FROM (
  SELECT n_name AS nation,
         EXTRACT(YEAR FROM o_orderdate) AS o_year,
         l_extendedprice * (1 - l_discount) - ps_supplycost * l_quantity AS amount
  FROM part, supplier, lineitem, partsupp, orders, nation
  WHERE s_suppkey = l_suppkey
    AND ps_suppkey = l_suppkey
    AND ps_partkey = l_partkey
    AND p_partkey = l_partkey
    AND o_orderkey = l_orderkey
    AND s_nationkey = n_nationkey
    AND p_name LIKE '%medium%'
) profit
GROUP BY nation, o_year
ORDER BY nation, o_year DESC;
SQL
)

Q10=$(cat <<'SQL'
SELECT c_custkey, c_name,
       sum(l_extendedprice * (1 - l_discount)) AS revenue,
       c_acctbal, n_name, c_address, c_phone, c_comment
FROM customer, orders, lineitem, nation
WHERE c_custkey = o_custkey
  AND l_orderkey = o_orderkey
  AND o_orderdate >= STR_TO_DATE('1994-02-01', '%Y-%m-%d')
  AND o_orderdate < DATE_ADD(STR_TO_DATE('1994-02-01', '%Y-%m-%d'), INTERVAL 3 MONTH)
  AND l_returnflag = 'R'
  AND c_nationkey = n_nationkey
GROUP BY c_custkey, c_name, c_acctbal, c_phone, n_name, c_address, c_comment
ORDER BY revenue DESC;
SQL
)

Q11=$(cat <<'SQL'
SELECT ps_partkey, sum(ps_supplycost * ps_availqty) AS value
FROM partsupp, supplier, nation
WHERE ps_suppkey = s_suppkey
  AND s_nationkey = n_nationkey
  AND n_name = 'VIETNAM'
GROUP BY ps_partkey
HAVING sum(ps_supplycost * ps_availqty) > (
  SELECT sum(ps_supplycost * ps_availqty) * 0.0001000000
  FROM partsupp, supplier, nation
  WHERE ps_suppkey = s_suppkey
    AND s_nationkey = n_nationkey
    AND n_name = 'VIETNAM'
)
ORDER BY value DESC;
SQL
)

Q12=$(cat <<'SQL'
SELECT l_shipmode,
       sum(CASE WHEN o_orderpriority = '1-URGENT' OR o_orderpriority = '2-HIGH' THEN 1 ELSE 0 END) AS high_line_count,
       sum(CASE WHEN o_orderpriority <> '1-URGENT' AND o_orderpriority <> '2-HIGH' THEN 1 ELSE 0 END) AS low_line_count
FROM orders, lineitem
WHERE o_orderkey = l_orderkey
  AND l_shipmode IN ('MAIL', 'TRUCK')
  AND l_commitdate < l_receiptdate
  AND l_shipdate < l_commitdate
  AND l_receiptdate >= STR_TO_DATE('1993-01-01', '%Y-%m-%d')
  AND l_receiptdate < DATE_ADD(STR_TO_DATE('1993-01-01', '%Y-%m-%d'), INTERVAL 1 YEAR)
GROUP BY l_shipmode
ORDER BY l_shipmode;
SQL
)

Q13=$(cat <<'SQL'
SELECT c_count, count(*) AS custdist
FROM (
  SELECT c_custkey, count(o_orderkey) AS c_count
  FROM customer
  LEFT JOIN orders ON c_custkey = o_custkey
                   AND o_comment NOT LIKE '%unusual%packages%'
  GROUP BY c_custkey
) c_orders
GROUP BY c_count
ORDER BY custdist DESC, c_count DESC;
SQL
)

Q14=$(cat <<'SQL'
SELECT 100.00 * sum(CASE WHEN p_type LIKE 'PROMO%' THEN l_extendedprice * (1 - l_discount) ELSE 0 END)
       / sum(l_extendedprice * (1 - l_discount)) AS promo_revenue
FROM lineitem, part
WHERE l_partkey = p_partkey
  AND l_shipdate >= STR_TO_DATE('1993-10-01', '%Y-%m-%d')
  AND l_shipdate < DATE_ADD(STR_TO_DATE('1993-10-01', '%Y-%m-%d'), INTERVAL 1 MONTH);
SQL
)

Q16=$(cat <<'SQL'
SELECT p_brand, p_type, p_size, count(DISTINCT ps_suppkey) AS supplier_cnt
FROM partsupp, part
WHERE p_partkey = ps_partkey
  AND p_brand <> 'Brand#53'
  AND p_type NOT LIKE 'PROMO BRUSHED%'
  AND p_size IN (18, 36, 24, 20, 5, 17, 15, 46)
  AND ps_suppkey NOT IN (
    SELECT s_suppkey
    FROM supplier
    WHERE s_comment LIKE '%Customer%Complaints%'
  )
GROUP BY p_brand, p_type, p_size
ORDER BY supplier_cnt DESC, p_brand, p_type, p_size;
SQL
)

Q17=$(cat <<'SQL'
SELECT sum(l_extendedprice) / 7.0 AS avg_yearly
FROM lineitem, part
WHERE p_partkey = l_partkey
  AND p_brand = 'Brand#35'
  AND p_container = 'LG CAN'
  AND l_quantity < (
    SELECT 0.2 * avg(l_quantity)
    FROM lineitem
    WHERE l_partkey = p_partkey
  );
SQL
)

Q18=$(cat <<'SQL'
SELECT c_name, c_custkey, o_orderkey, o_orderdate, o_totalprice, sum(l_quantity)
FROM customer, orders, lineitem
WHERE o_orderkey IN (
  SELECT l_orderkey
  FROM lineitem
  GROUP BY l_orderkey
  HAVING sum(l_quantity) > 315
)
AND c_custkey = o_custkey
AND o_orderkey = l_orderkey
GROUP BY c_name, c_custkey, o_orderkey, o_orderdate, o_totalprice
ORDER BY o_totalprice DESC, o_orderdate;
SQL
)

Q19=$(cat <<'SQL'
SELECT sum(l_extendedprice * (1 - l_discount)) AS revenue
FROM lineitem, part
WHERE
  (p_partkey = l_partkey AND p_brand = 'Brand#24'
   AND p_container IN ('SM CASE', 'SM BOX', 'SM PACK', 'SM PKG')
   AND l_quantity >= 2 AND l_quantity <= 2 + 10
   AND p_size BETWEEN 1 AND 5
   AND l_shipmode IN ('AIR', 'AIR REG')
   AND l_shipinstruct = 'DELIVER IN PERSON')
OR
  (p_partkey = l_partkey AND p_brand = 'Brand#32'
   AND p_container IN ('MED BAG', 'MED BOX', 'MED PKG', 'MED PACK')
   AND l_quantity >= 19 AND l_quantity <= 19 + 10
   AND p_size BETWEEN 1 AND 10
   AND l_shipmode IN ('AIR', 'AIR REG')
   AND l_shipinstruct = 'DELIVER IN PERSON')
OR
  (p_partkey = l_partkey AND p_brand = 'Brand#12'
   AND p_container IN ('LG CASE', 'LG BOX', 'LG PACK', 'LG PKG')
   AND l_quantity >= 24 AND l_quantity <= 24 + 10
   AND p_size BETWEEN 1 AND 15
   AND l_shipmode IN ('AIR', 'AIR REG')
   AND l_shipinstruct = 'DELIVER IN PERSON');
SQL
)

Q20=$(cat <<'SQL'
SELECT s_name, s_address
FROM supplier, nation
WHERE s_suppkey IN (
  SELECT ps_suppkey
  FROM partsupp
  WHERE ps_partkey IN (
    SELECT p_partkey FROM part WHERE p_name LIKE 'pink%'
  )
  AND ps_availqty > (
    SELECT 0.5 * sum(l_quantity)
    FROM lineitem
    WHERE l_partkey = ps_partkey
      AND l_suppkey = ps_suppkey
      AND l_shipdate >= STR_TO_DATE('1995-01-01', '%Y-%m-%d')
      AND l_shipdate < DATE_ADD(STR_TO_DATE('1995-01-01', '%Y-%m-%d'), INTERVAL 1 YEAR)
  )
)
AND s_nationkey = n_nationkey
AND n_name = 'INDIA'
ORDER BY s_name;
SQL
)

Q21=$(cat <<'SQL'
SELECT s_name, count(*) AS numwait
FROM supplier, lineitem l1, orders, nation
WHERE s_suppkey = l1.l_suppkey
  AND o_orderkey = l1.l_orderkey
  AND o_orderstatus = 'F'
  AND l1.l_receiptdate > l1.l_commitdate
  AND EXISTS (
    SELECT * FROM lineitem l2
    WHERE l2.l_orderkey = l1.l_orderkey
      AND l2.l_suppkey <> l1.l_suppkey
  )
  AND NOT EXISTS (
    SELECT * FROM lineitem l3
    WHERE l3.l_orderkey = l1.l_orderkey
      AND l3.l_suppkey <> l1.l_suppkey
      AND l3.l_receiptdate > l3.l_commitdate
  )
  AND s_nationkey = n_nationkey
  AND n_name = 'IRAQ'
GROUP BY s_name
ORDER BY numwait DESC, s_name;
SQL
)

Q22=$(cat <<'SQL'
SELECT cntrycode, count(*) AS numcust, sum(c_acctbal) AS totacctbal FROM ( SELECT substring(c_phone FROM 1 FOR 2) AS cntrycode, c_acctbal 
FROM customer 
WHERE substring(c_phone FROM 1 FOR 2) IN ( '18',  '11',  '17',  '12',  '32',  '22',  '23' ) AND c_acctbal > ( 
  SELECT avg(c_acctbal) 
  FROM customer WHERE c_acctbal > 0.00 AND substring(c_phone FROM 1 FOR 2) IN ( '18',  '11',  '17',  '12',  '32',  '22',  '23' ) ) AND NOT EXISTS ( 
    SELECT * FROM orders WHERE o_custkey = c_custkey 
  ) 
) custsale GROUP BY cntrycode ORDER BY cntrycode;
SQL
)

Q22_simple=$(cat <<'SQL'
select cntrycode, count(*) as numcust, sum(c_acctbal) as totacctbal 
from ( 
  select substring(c_phone from 1 for 2) as cntrycode, c_acctbal 
  from customer 
  where substring(c_phone from 1 for 2) in ('18', '11', '17', '12', '32', '22', '23') and c_acctbal > 4983.784107 and not exists ( 
    select * from orders where o_custkey = c_custkey 
  ) 
) as custsale group by cntrycode order by cntrycode; 
SQL
)

ORDER=(Q01 Q02 Q03 Q04 Q05 Q06 Q07 Q08 Q09 Q10 Q11 Q12 Q13 Q14 Q16 Q17 Q18 Q19 Q20 Q21 Q22 Q22_simple)

run_one() {
  local name="$1"
  local sql="$2"

  mysql -h"$HOST" -P"$PORT" -u"$USER" -p"$PASS" --database="$DB" --raw <<SQL >/dev/null
SET optimizer_trace="enabled=on", SESSION optimizer_trace_max_mem_size=4294967295;

\T $OUTDIR/${name}.explain.json
EXPLAIN FORMAT=JSON ${sql}
\t

\T $OUTDIR/${name}.trace.txt
SELECT trace FROM INFORMATION_SCHEMA.OPTIMIZER_TRACE\G
\t

QUIT
SQL
  echo "Done: $name -> $OUTDIR/${name}.explain.json, $OUTDIR/${name}.trace.txt"
}

# --- Execute ---
for key in "${ORDER[@]}"; do
  run_one "$key" "${!key}"
done