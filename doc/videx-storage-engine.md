# VIDEX for MariaDB: Plugin + VIDEX-Server

This document explains how to install and use **VIDEX** with MariaDB, including:

- Installing/enabling the **VIDEX plugin** in MariaDB
- Running the **VIDEX-Server** (statistics service) as a container
- Running a one-shot **videx-sync** workflow to build a VIDEX database
- Comparing `EXPLAIN` between your original schema and the VIDEX schema

If you are looking for the VIDEX server repository (more examples and extension points), see:

- VIDEX server repository: `https://github.com/bytedance/videx/`
- Example dataset (TPC-H tiny): `https://github.com/bytedance/videx/blob/main/data/tpch_tiny/tpch_tiny.sql.tar.gz`

---

## Prerequisites

- A running MariaDB server you can connect to (the “target”).
- A MariaDB build that includes the `VIDEX` engine plugin (the “MariaDB-VIDEX”).
  - For a quick start, the target MariaDB and MariaDB-VIDEX can be the same instance.
- Docker (to run VIDEX-Server and videx-sync).

## 1. What is VIDEX

VIDEX is a **virtual/hypothetical index engine** for what-if analysis.

- **Goal**: Evaluate how potential indexes (and optimizer decisions such as join orders) would change query plans *without creating real indexes on production data*.
- **How it works**: VIDEX replays optimizer / handler calls using **statistics** (cardinality, NDV, histograms, etc.) instead of reading table data. Complex statistics computation is offloaded to an external service (**VIDEX-Server**) via HTTP.

In practice, you keep your existing MariaDB schema and data as the “target”, and create a second schema whose tables use `ENGINE=VIDEX`. You then run `EXPLAIN` on both schemas and compare plans.

> Research note (AI4DB)
>
> Estimating **multi-column joint NDV (Number of Distinct Value)** and **cardinality** is a challenging research problem. You can extend VIDEX by implementing your own estimation models in **VIDEX-Server** to improve accuracy for your workload.

---

## 2. Components and roles

VIDEX typically involves the following roles:

- **Target MariaDB**: your original database instance and schema (contains real data).
- **MariaDB with VIDEX plugin** ("MariaDB-VIDEX"): a MariaDB instance that has the `VIDEX` storage engine plugin enabled.
  - It can be the *same* instance as the Target MariaDB (common for a quick start).
  - Or it can be a separate MariaDB instance used only for what-if analysis.
- **VIDEX-Server**: a standalone HTTP service that stores metadata/statistics and answers estimation requests from the VIDEX plugin.

This doc focuses on a **docker-based workflow** for VIDEX-Server and `videx-sync`, so users can complete the VIDEX end-to-end flow with a few `docker` commands, while the MariaDB server itself is managed by users.

---

## 3. Prepare sample data (TPC-H tiny)

You can test VIDEX with the `TPC-H tiny` sample.

1) Download `tpch_tiny.sql.tar.gz` from:

`https://github.com/bytedance/videx/blob/main/data/tpch_tiny/tpch_tiny.sql.tar.gz`

2) Create a database and import the data (example using `mariadb` client):

```bash
mariadb -h<TARGET_HOST> -P<TARGET_PORT> -u<TARGET_USER> -p<TARGET_PASS> \
  -e "CREATE DATABASE tpch_tiny;"

tar -zxf tpch_tiny.sql.tar.gz
mariadb -h<TARGET_HOST> -P<TARGET_PORT> -u<TARGET_USER> -p<TARGET_PASS> \
  -Dtpch_tiny < tpch_tiny.sql
```

---

## 4. Install / enable the VIDEX plugin (MariaDB)

### 4.1 Verify the engine

Connect to your MariaDB instance and check whether `VIDEX` engine is available:

```sql
SHOW ENGINES;
```

If you see a row for `VIDEX` with `SUPPORT` as `YES` or `DEFAULT`, the engine is available.

### 4.2 Build-time enablement

If `VIDEX` is not present, build MariaDB with VIDEX enabled. The MariaDB server PR that introduced VIDEX is:

`https://github.com/MariaDB/server/pull/4217`

Key dependencies and options:

- Dependencies:
  - `libcurl` (HTTP client)
  - `zlib` (compression)
- CMake options:
  - `-DPLUGIN_VIDEX=YES` (enable plugin)
  - `-DPLUGIN_VIDEX=STATIC` (static)
  - `-DPLUGIN_VIDEX=DYNAMIC` (dynamic)

Example build configuration:

```bash
cmake -DPLUGIN_VIDEX=YES \
      -DCMAKE_CXX_COMPILER=/usr/bin/clang++ \
      -G Ninja --fresh \
      -S /path/to/mariadb \
      -B /path/to/build
```

---

## 5. Install and run VIDEX-Server (Docker)

VIDEX-Server is a separate service providing statistics/estimation over HTTP, and MariaDB-VIDEX calls it to get 
statistics information for generating query plans.

### 5.1 Images

Public images:

- Docker Hub: `kangrongme/videx-server:0.2.0`

### 5.2 Start the server

Expose container port `5001`:

```bash
docker run -d --name videx-server \
  -p 5001:5001 \
  kangrongme/videx-server:0.2.0
```

Then the service is reachable at:

- `http://<YOUR_HOST_IP>:5001`

> Reachability note
>
> Prefer using a **routable IP address** (your host/server IP) instead of `localhost/127.0.0.1`.
> This matters because both MariaDB-VIDEX (the plugin) and `videx-sync` need to reach VIDEX-Server. If any of them run inside a container, `localhost/127.0.0.1` refers to that container itself (not your host), so the service will not be reachable via `localhost`.

---

## 6. Build the VIDEX schema (videx-sync)

VIDEX-Server image supports two entrypoint modes:

- `server` (default): start VIDEX-Server
- `sync`: run a one-shot workflow to collect metadata from `--target`, then:
  - add metadata into VIDEX-Server
  - create virtual tables in `--videx`

### 6.1 Command template

```bash
docker run --rm --name videx-sync \
  kangrongme/videx-server:0.2.0 sync \
  --target <TARGET_HOST>:<TARGET_PORT>:<TARGET_DB>:<TARGET_USER>:<TARGET_PASS> \
  [--videx <VIDEX_HOST>:<VIDEX_PORT>:<VIDEX_DB>:<VIDEX_USER>:<VIDEX_PASS>] \
  [--videx_server <VIDEX_SERVER_HOST>:<VIDEX_SERVER_PORT>]
```

Notes:

1) If `--videx` is not specified, a default database `videx_{TARGET_DB}` will be created in `--target`.
2) If you run a separate MariaDB-VIDEX instance, pass that instance as `--videx`.
3) If your VIDEX-Server is not `<TARGET_HOST>:5001`, pass `--videx_server` explicitly.


### 6.2 If you used localhost and it failed

Inside a container, `localhost/127.0.0.1` refers to the container itself.

On Linux Docker Engine, you can reach the host via `host.docker.internal` using `--add-host`:

```bash
docker run --rm --name videx-sync \
  --add-host=host.docker.internal:host-gateway \
  kangrongme/videx-server:0.2.0 sync \
  --target host.docker.internal:<PORT>:<DB>:<USER>:<PASS> \
  --videx host.docker.internal:<PORT>:<VIDEX_DB>:<VIDEX_USER>:<VIDEX_PASS> \
  --videx_server host.docker.internal:<VIDEX_SERVER_PORT>
```

However, if MariaDB-VIDEX itself is also running in a container, reachability can become tricky.
Using a routable IP is the most robust approach.

---

## 7. Configure the plugin (status/system variables)

On MariaDB, the VIDEX plugin exposes **session** system variables.

```sql
SHOW VARIABLES LIKE '%videx_server_ip%';
```

Example output:

```text
+-----------------+----------------+
| Variable_name   | Value          |
+-----------------+----------------+
| videx_server_ip | 127.0.0.1:5001 |
+-----------------+----------------+
```

- `videx_server_ip`: **critical**. The address (`host:port`) that MariaDB-VIDEX uses to call VIDEX-Server.

Configure them for your current session before running `EXPLAIN` on `ENGINE=VIDEX` tables:

```sql
SET SESSION videx_server_ip = '<VIDEX_SERVER_HOST>:<VIDEX_SERVER_PORT>';
```

---

## 8. Quick start (Target MariaDB == MariaDB-VIDEX)

This section assumes:

- Users already have **one MariaDB instance** running.
- Users want to create the VIDEX schema **in the same instance** (so “MariaDB-VIDEX == Target MariaDB”).
- User's MariaDB is already running and reachable.
- The routable IP is `203.0.113.42` (example only).
- MariaDB is reachable at `203.0.113.42:15508` (example only).
- VIDEX-Server will be reachable at `203.0.113.42:5001` (example only).
- User/password: `videx` / `password`.

### Step 1: Start VIDEX-Server

```bash
docker run -d --name videx-server \
  -p 5001:5001 \
  kangrongme/videx-server:0.2.0
```

### Step 2: Build VIDEX schema via videx-sync

```bash
docker run --rm --name videx-sync \
  kangrongme/videx-server:0.2.0 sync \
  --target 203.0.113.42:15508:tpch_tiny:videx:password \
  --videx  203.0.113.42:15508:videx_tpch_tiny:videx:password \
  --videx_server 203.0.113.42:5001
```

### Step 3: EXPLAIN on the original schema

Run `EXPLAIN` on your original tables:

```sql
USE tpch_tiny;
SET SESSION use_stat_tables = NEVER;
EXPLAIN SELECT s_name, count(*) AS numwait FROM supplier, lineitem l1, orders, nation WHERE s_suppkey = l1.l_suppkey AND o_orderkey = l1.l_orderkey AND o_orderstatus = 'F' AND l1.l_receiptdate > l1.l_commitdate AND EXISTS (SELECT * FROM lineitem l2 WHERE l2.l_orderkey = l1.l_orderkey AND l2.l_suppkey <> l1.l_suppkey) AND NOT EXISTS (SELECT * FROM lineitem l3 WHERE l3.l_orderkey = l1.l_orderkey AND l3.l_suppkey <> l1.l_suppkey AND l3.l_receiptdate > l3.l_commitdate) AND s_nationkey = n_nationkey AND n_name = 'IRAQ' GROUP BY s_name ORDER BY numwait DESC, s_name; 

```

> Note: Collecting histograms may change MariaDB’s cardinality estimates (i.e., histogram-based estimates rather than InnoDB index statistics). Since VIDEX aims to simulate InnoDB index engine behavior, users can set `SET SESSION use_stat_tables = NEVER;` to make `EXPLAIN` results more similar between InnoDB and the VIDEX engine.

The `EXPLAIN` output for the original schema is:

```
+----+--------------------+----------+--------+-------------------------------------------------------+--------------+---------+--------------------------------+-------+----------------------------------------------+
| id | select_type        | table    | type   | possible_keys                                         | key          | key_len | ref                            | rows  | Extra                                        |
+----+--------------------+----------+--------+-------------------------------------------------------+--------------+---------+--------------------------------+-------+----------------------------------------------+
| 1  | PRIMARY            | orders   | ALL    | PRIMARY                                               | <null>       | <null>  | <null>                         | 14944 | Using where; Using temporary; Using filesort |
| 1  | PRIMARY            | l1       | ref    | LINEITEM_UK1,LINEITEM_FK1                             | LINEITEM_FK1 | 4       | tpch_tiny.orders.O_ORDERKEY    | 1     | Using where                                  |
| 1  | PRIMARY            | supplier | eq_ref | PRIMARY,SUPPLIER_FK1,idx_S_NATIONKEY_S_SUPPKEY_S_NAME | PRIMARY      | 4       | tpch_tiny.l1.L_SUPPKEY         | 1     |                                              |
| 1  | PRIMARY            | nation   | eq_ref | PRIMARY                                               | PRIMARY      | 4       | tpch_tiny.supplier.S_NATIONKEY | 1     | Using where                                  |
| 1  | PRIMARY            | l2       | ref    | LINEITEM_UK1,LINEITEM_FK1                             | LINEITEM_FK1 | 4       | tpch_tiny.orders.O_ORDERKEY    | 1     | Using where; FirstMatch(nation)              |
| 3  | DEPENDENT SUBQUERY | l3       | ref    | LINEITEM_UK1,LINEITEM_FK1                             | LINEITEM_UK1 | 4       | tpch_tiny.l1.L_ORDERKEY        | 1     | Using where                                  |
+----+--------------------+----------+--------+-------------------------------------------------------+--------------+---------+--------------------------------+-------+----------------------------------------------+
```

### Step 4: EXPLAIN on the VIDEX schema

Run `EXPLAIN` on the VIDEX schema (tables are `ENGINE=VIDEX`):

```sql
USE videx_tpch_tiny;
SET SESSION videx_server_ip = '203.0.113.42:5001';
EXPLAIN SELECT s_name, count(*) AS numwait FROM supplier, lineitem l1, orders, nation WHERE s_suppkey = l1.l_suppkey AND o_orderkey = l1.l_orderkey AND o_orderstatus = 'F' AND l1.l_receiptdate > l1.l_commitdate AND EXISTS (SELECT * FROM lineitem l2 WHERE l2.l_orderkey = l1.l_orderkey AND l2.l_suppkey <> l1.l_suppkey) AND NOT EXISTS (SELECT * FROM lineitem l3 WHERE l3.l_orderkey = l1.l_orderkey AND l3.l_suppkey <> l1.l_suppkey AND l3.l_receiptdate > l3.l_commitdate) AND s_nationkey = n_nationkey AND n_name = 'IRAQ' GROUP BY s_name ORDER BY numwait DESC, s_name; 
```

The `EXPLAIN` output for the VIDEX schema is:

```
+----+--------------------+----------+--------+-------------------------------------------------------+--------------+---------+--------------------------------------+-------+----------------------------------------------+
| id | select_type        | table    | type   | possible_keys                                         | key          | key_len | ref                                  | rows  | Extra                                        |
+----+--------------------+----------+--------+-------------------------------------------------------+--------------+---------+--------------------------------------+-------+----------------------------------------------+
| 1  | PRIMARY            | orders   | ALL    | PRIMARY                                               | <null>       | <null>  | <null>                               | 14883 | Using where; Using temporary; Using filesort |
| 1  | PRIMARY            | l1       | ref    | LINEITEM_UK1,LINEITEM_FK1                             | LINEITEM_FK1 | 4       | videx_tpch_tiny.orders.O_ORDERKEY    | 1     | Using where                                  |
| 1  | PRIMARY            | supplier | eq_ref | PRIMARY,SUPPLIER_FK1,idx_S_NATIONKEY_S_SUPPKEY_S_NAME | PRIMARY      | 4       | videx_tpch_tiny.l1.L_SUPPKEY         | 1     |                                              |
| 1  | PRIMARY            | nation   | eq_ref | PRIMARY                                               | PRIMARY      | 4       | videx_tpch_tiny.supplier.S_NATIONKEY | 1     | Using where                                  |
| 1  | PRIMARY            | l2       | ref    | LINEITEM_UK1,LINEITEM_FK1                             | LINEITEM_FK1 | 4       | videx_tpch_tiny.orders.O_ORDERKEY    | 1     | Using where; FirstMatch(nation)              |
| 3  | DEPENDENT SUBQUERY | l3       | ref    | LINEITEM_UK1,LINEITEM_FK1                             | LINEITEM_UK1 | 4       | videx_tpch_tiny.l1.L_ORDERKEY        | 1     | Using where                                  |
+----+--------------------+----------+--------+-------------------------------------------------------+--------------+---------+--------------------------------------+-------+----------------------------------------------+
```

Compare the output between Step 3 and Step 4.

---

## 9. Notes and best practices

1) `videx-sync` can be time-consuming on large schemas, because it needs to collect metadata/statistics.
   The metadata collection method is extensible; the VIDEX source repository also discusses lighter-weight sampling approaches.

2) Networking matters. Since VIDEX-Server is often in a container, `localhost/127.0.0.1` may not refer to what you expect.
    The routable IP is recommended for reachability, as it ensures that both MariaDB-VIDEX and the container can reach it.