

# VIDEX

<p align="center">
  <a href="./README.md">English</a> |
  <a href="./README_zh.md">简体中文</a>
</p>


**VIDEX**: The Disaggregated, Extensible **\[VI\]**rtual in**\[DEX\]** Engine for What-If Analysis in MySQL 🚀
- **Virtual Index**: Does not require real data, relies only on statistical information and algorithm models to accurately simulate query plans, table join orders, and index selections;
- **Decoupled**: VIDEX can be deployed on a separate instance with no impact on the production MySQL environment.
- **Scalable**: VIDEX offers convenient interfaces allowing users to apply models like `cardinality` and `ndv` to downstream MySQL tasks (e.g., index recommendation);


The `virtual index` (aka `hypothetical index`) aims to simulate the cost of indexes within SQL query plans, 
thereby demonstrating to users the impact of indexes on SQL plans without the need to create actual indexes on raw instances.
This technology is widely applied in various SQL optimization tasks, including index recommendation and table join order optimization.
As a reference, many other databases already have virtual index features from official or third-party sources,
such as [Postgres](https://github.com/HypoPG/hypopg), 
[Oracle](https://oracle-base.com/articles/misc/virtual-indexes), 
and [IBM DB2](https://www.ibm.com/docs/en/db2-for-zos/12?topic=tables-dsn-virtual-indexes).

> **Note:** The term `virtual index` used here is distinct from the "virtual index" referenced in the 
> [MySQL Official Documents](https://dev.mysql.com/doc/refman/8.4/en/create-table-secondary-indexes.html), 
> which refers to indexes built on virtual generated columns.

Additionally, VIDEX encapsulates a set of standardized interfaces for cost estimation, 
addressing popular topics in academic research such as **cardinality estimation** and **NDV (Number of Distinct Values) estimation**. 
Researchers and database developers can easily integrate custom algorithms into VIDEX for optimization tasks. 
By default, VIDEX includes implementations based on histograms and NDV collected from the `ANALYZE TABLE` or small-scale data sampling.

VIDEX offers two startup modes:

1. **Plugin to production database**: Install VIDEX as a plugin to the production database instance.
2. **Individual instance**: This mode can completely avoid impacting the stability of online running instances, making it practical for industrial environments.

Functionally, VIDEX supports creating and deleting indexes (single-column indexes, composite indexes, EXTENDED_KEYS indexes). 
However, it currently does not support functional indexes, FULL-Text, and Spatial Indexes. 

In terms of **accuracy**, we have tested VIDEX on complex analytical benchmarks such as `TPC-H`, `TPC-H-Skew`, and `JOB`.
<font color="red">Given only the oracle NDV and cardinality, **the VIDEX query plan is 100% identical to InnoDB**.</font> 
(Refer to [Example: TPC-H](#example-tpch) for additional details). 
We expect that VIDEX can provide users with a better platform to more easily test the effectiveness of cardinality and NDV algorithms, and apply them on SQL optimization tasks.

---


# Overview

<p align="center">
  <img src="doc/videx-structure.png" width="600">
</p>

VIDEX consists of two parts:

- **VIDEX-MySQL**: Conducted a thorough review of over 90 interface functions in the MySQL handler, and implement the index-related parts.
- **VIDEX-Statistic-Server**: The cost estimation service calculates NDV and Cardinality based on collected statistical information and estimation algorithms, and returns the results to the VIDEX-MySQL instance. 

VIDEX creates an individual virtual database according to the specified target database in the raw instance,
containing a series of tables with the same DDL, but replacing the engine from `InnoDB` to `VIDEX`.

# Startup VIDEX-MySQL and VIDEX-Statistic-Server

## From Docker Image

```shell
docker run -itd --name videx -p 13383:3306 -p 5001:5001 \
--entrypoint=/bin/bash hub.byted.org/boe/toutiao.mysql.sqlbrain_parse_80:54a3bf649b5c6e0795954669ee4447b9 \
-c "cd /opt/tiger/mysql-server && bash init_start.sh"
```

The dockerhub version will come soon.

Considering the complexity of compiling VIDEX-MySQL, a Docker image has been created for ease of use. This image includes both the VIDEX-MySQL instance and the VIDEX-Statistic-Server, with the VIDEX engine plugin already installed. It is based on [Percona-MySQL release-8.0.34-26](https://github.com/percona/percona-server/tree/release-8.0.34-26), where Percona-MySQL is a fully compatible, enhanced version of MySQL.

VIDEX-Statistic-Server and VIDEX-MySQL are decoupled; users can add new cost estimation algorithms (NDV, cardinality, index cache pct), start their own VIDEX-Statistic-Server, and specify the IP of the VIDEX Statistic Server when executing queries.


## From Source Code
### Compile VIDEX-MySQL Plugin

Clone the MySQL or Percona server (verified with MySQL-server 8.0+ and Percona-server 8.0.34-26+).

```bash
MySQL8_HOME=MySQL8_Server_Source
# mysql
git clone --depth=1 --recursive -b 8.0 https://github.com/mysql/mysql-server.git $MySQL8_HOME
# percona
git clone --depth=1 --recursive -b release-8.0.34-26 https://github.com/percona/percona-server.git $MySQL8_HOME

```

copy VIDEX-MySQL codes into `$MySQL8_HOME/storage`:

```bash
cp -r $VIDEX_HOME/src/mysql/videx $MySQL8_HOME/storage
```

Generate the necessary Makefile with cmake.

```bash
cmake .. \
    -B./build \
    -DWITH_DEBUG=0 \
    -DCMAKE_INSTALL_PREFIX=. \
    -DMYSQL_DATADIR=./data \
    -DSYSCONFDIR=./etc \
    -DWITH_BOOST=../boost \
    -DDOWNLOAD_BOOST=1 \
    -DWITH_ROCKSDB=OFF
```

Navigate to the videx directory and compile videx individually.

```bash
cd $MySQL8_HOME/build/storage/videx/
make -j `nproc`
```

Store the generated `ha_videx.so` in `plugin_dir`:

```sql
SHOW VARIABLES LIKE "%plugin%"
    -> ;
+-----------------------------------------------+-----------------------------------------------+
| Variable_name                                 | Value                                         |
+-----------------------------------------------+-----------------------------------------------+
| default_authentication_plugin                 | caching_sha2_password                         |
| plugin_dir                                    | /root/mysql8/lib/plugin/ |
| replication_optimize_for_static_plugin_config | OFF                                           |
+-----------------------------------------------+-----------------------------------------------+

cp ha_videx.so /root/mysql8/lib/plugin/
```

Install the plugin.

```sql
INSTALL PLUGIN VIDEX SONAME 'ha_videx.so';
UNINSTALL PLUGIN VIDEX;
```

Verify that VIDEX has been installed. You will see a new engine VIDEX.

```sql
SHOW ENGINES;
```

### Startup Videx-Stats-Server
We recommend using Anaconda or Miniconda to create a standalone Python environment, then install VIDEX.

```bash
cd $VIDEX_HOME

conda create -n videx_py39 python=3.9

conda activate videx_py39

pip install -e . -r requirements.txt
```

Specify the port for Videx-Stats-Server and start the service.

```bash
cd $VIDEX_HOME/src/sub_platforms/sql_opt/videx/scripts
python start_videx_server.py --port 5001
```

## Import VIDEX Metadata and Do EXPLAIN

Specify the connection details for the original database and the videx-stats-server. 
Gather statistics from the original database, save them to an intermediate file, 
then import them into the VIDEX database.

> - If VIDEX-MySQL is started independently rather than as a plugin on the target-MySQL, users can specify the VIDEX-MySQL address using the `--videx` parameter.
> - If VIDEX-Server is started independently rather than being deployed on the same machine as VIDEX-MySQL, users can specify the VIDEX-Server address using the `--videx_server` parameter.
> - If metadata files have already been generated, users can specify the `--meta_path` parameter to skip the collection process.

```bash
cd $VIDEX_HOME/src/sub_platforms/sql_opt/videx/scripts
python videx_build_env.py --target 127.0.0.1:13383:tpch_sf1:user:password \
[--target 127.0.0.1:13309:videx_tpch_sf1:user:password] \
[--videx_server 127.0.0.1:5001] \
[--meta_path /path/to/file]

```

You can use MySQL's native DDL syntax to create indexes, without any adaption and modification.

```sql
ALTER TABLE t1 ADD INDEX idx_videx_c1c2(c1, c2);
```

The only difference introduced by VIDEX is that you need to set the address of the videx-stats-server before querying. 
Then, you can then use `EXPLAIN SQL` to obtain the query plan and see the impact of VIDEX virtual indexes.

> - The default value for `VIDEX_SERVER` is `127.0.0.1:5001`.
> - If VIDEX-MySQL and VIDEX-Server are deployed on the same instance or machine, there is no need to specify `SET @VIDEX_SERVER`.

```sql
SET @VIDEX_SERVER='127.0.0.1:5001';
EXPLAIN select * from t1 where c2 > 10 and c1 = 5
```

Explain results are displayed as follows:

```sql
+----+-------------+-------+------------+-------+------------------------+---------+---------+-------+------+----------+--------+
| id | select_type | table | partitions | type  | possible_keys          | key     | key_len | ref   | rows | filtered | Extra  |
+----+-------------+-------+------------+-------+------------------------+---------+---------+-------+------+----------+--------+
| 1  | SIMPLE      | t1    | <null>     | const | PRIMARY,idx_videx_c1c2 | PRIMARY | 4       | const | 1    | 100.0    | <null> |
+----+-------------+-------+------------+-------+------------------------+---------+---------+-------+------+----------+--------+
```

Use MySQL's native DDL syntax to delete indexes.

```sql
ALTER TABLE t1 DROP INDEX idx_videx_c1c2(c1, c2);
```

## <a id="example-tpch">Example: TPC-H</a>
### TPC-H tiny

In this example, we will start by importing data from TPC-H-tiny, which randomly samples 1% of the data from TPC-H sf1(1g), 
to demonstrate how to use VIDEX.

To demonstrate the effectiveness of VIDEX, we compare the explain details on TPC-H Q21, 
a complex query involving a 4-table join that includes various elements such as `WHERE`, `aggregation`, `ORDER BY`, 
`GROUP BY`, `EXISTS`, and `self-join`. There are 11 indexes on 4 tables available for MySQL to choose from.

**Prepare VIDEX Environment**

Given a target database (target-MySQL), users can independently start `VIDEX-MySQL` and `VIDEX-Server` on any node.

Particularly, launching VIDEX through Docker is the simplest approach. The VIDEX Docker container includes 
both `VIDEX-MySQL` and `VIDEX-Server` deployed on the same instance, simplifying many parameter configurations.

```shell
# TODO: The following image is ByteDance's image. In the next step, it will be replaced with the Docker Hub image.
docker run -itd --name videx -p 13383:3306 -p 5001:5001 \
--entrypoint=/bin/bash hub.byted.org/boe/toutiao.mysql.sqlbrain_parse_80:54a3bf649b5c6e0795954669ee4447b9 \
-c "cd /opt/tiger/mysql-server && bash init_start.sh"
```

We assume the user environment is as follows:
- `target-MySQL`: The target instance (production database) with the address 127.0.0.1:13383:tpch_tiny:user:password.
- `VIDEX-MySQL`: An instance with the VIDEX plugin installed, located on the production database with the same address.
- `VIDEX-Server`: The VIDEX metadata and algorithm server installed on the same node, running on the default port. Address: 127.0.0.1:5001.

**Import TPCH-Tiny**

Import TPCH-tiny.sql into the target instance.

```shell
cd $VIDEX_HOME

mysql -h127.0.0.1 -P13383 -uroot -ppassword -e "create database tpch_tiny;"
tar -zxf data/tpch_tiny/tpch_tiny.sql.tar.gz
mysql -h127.0.0.1 -P13383 -uroot -ppassword -Dtpch_tiny < tpch_tiny.sql
```

**Import VIDEX Metadata**


```shell
pip install -e . -r requirements.txt # if the python env hasn't installed

python src/sub_platforms/sql_opt/videx/scripts/videx_build_env.py \
 --target 127.0.0.1:13383:tpch_sf1:user:password

```

The output is as follows:

```log
2025-02-17 13:46:48 [2855595:140670043553408] INFO     root            [videx_build_env.py:178] - Build env finished. Your VIDEX server is 127.0.0.1:5001.
You are running in non-task mode.
To use VIDEX, please set the following variable before explaining your SQL:
--------------------
-- Connect VIDEX-MySQL: mysql -h127.0.0.1 -P13383 -uroot -ppassowrd -Dvidex_tpch_tiny
USE videx_tpch_tiny;
SET @VIDEX_SERVER='127.0.0.1:5001';
-- EXPLAIN YOUR_SQL;
```

Now the metadata file has already been written to `videx_metadata_tpch_tiny.json` and imported into VIDEX-Server. 
If the metadata file is prepared in advance, users can specify `--meta_path` to bypass the collection process.

**EXPLAIN SQL**

Connect to VIDEX-MySQL and execute EXPLAIN. 
Since VIDEX-Server is deployed on the same node as VIDEX-MySQL and is running on the default port (5001), there is no need to set `VIDEX_SERVER` additionally.


```sql
-- SET @VIDEX_SERVER='127.0.0.1:5001'; 
EXPLAIN
FORMAT = JSON
SELECT s_name, count(*) AS numwait
FROM supplier,
     lineitem l1,
     orders,
     nation
WHERE s_suppkey = l1.l_suppkey
  AND o_orderkey = l1.l_orderkey
  AND o_orderstatus = 'F'
  AND l1.l_receiptdate > l1.l_commitdate
  AND EXISTS (SELECT *
              FROM lineitem l2
              WHERE l2.l_orderkey = l1.l_orderkey
                AND l2.l_suppkey <> l1.l_suppkey)
  AND NOT EXISTS (SELECT *
                  FROM lineitem l3
                  WHERE l3.l_orderkey = l1.l_orderkey
                    AND l3.l_suppkey <> l1.l_suppkey
                    AND l3.l_receiptdate > l3.l_commitdate)
  AND s_nationkey = n_nationkey
  AND n_name = 'IRAQ'
GROUP BY s_name
ORDER BY numwait DESC, s_name;
```

We compared VIDEX with InnoDB using `EXPLAIN FORMAT=JSON`, a more rigorous format. 
We evaluated not only the `table join order` and `index selection`,
but also every detail of the query plan, including the number of rows and cost at each step.

As shown in the following image, VIDEX (left) can generate a query plan almost 100% the same as InnoDB (right).
The complete EXPLAIN result files are located in `data/explain_result`.

![explain.png](doc/explain_tpch_tiny_compare.png)

Note that, The simulation accuracy of VIDEX dependencies on three crucial interfaces:
- `ndv`
- `cardinality` 
- `pct_cached` (the percentage of the index loaded into memory).

### TPC-H sf1

We also prepared a metadata file for TPC-H sf1: `data/videx_metadata_tpch_sf1.json`.

```shell
cd $VIDEX_HOME
python src/sub_platforms/sql_opt/videx/scripts/videx_build_env.py \
 --target 127.0.0.1:13383:tpch_sf1:user:password --videx_server 5001 \
 --meta_path data/videx_metadata_tpch_sf1.json

```

Consistent with TPCH-tiny, VIDEX can generate a query plan for` TPCH-sf1 Q21` that is almost identical to InnoDB's, 
as detailed in `data/tpch_sf1`.

![explain.png](doc/explain_tpch_sf1_compare.png)

## 🚀 Integrate Your Custom Model

### Method 1: Add into VIDEX-Statistic-Server

Users can fully implement `VidexModelBase`.

If users focus on cardinality and ndv (two popular research topics), 
they can also inherit from `VidexModelInnoDB` (see `VidexModelExample`).
`VidexModelInnoDB` abstracts away complexities such as system variables 
and index metadata formats, providing a basic (heuristic) algorithm for ndv and cardinality.

```python
class VidexModelBase(ABC):
    """
    Abstract cost model class. VIDEX-Statistic-Server receives requests from VIDEX-MySQL for Cardinality
    and NDV estimates, parses them into structured data for ease use of developers.

    Implement these methods to inject Cardinality and NDV algorithms into MySQL.
    """

    @abstractmethod
    def cardinality(self, idx_range_cond: IndexRangeCond) -> int:
        """
        Estimates the cardinality (number of rows matching a criteria) for a given index range condition.

        Parameters:
            idx_range_cond (IndexRangeCond): Condition object representing the index range.

        Returns:
            int: Estimated number of rows that match the condition.

        Example:
            where c1 = 3 and c2 < 3 and c2 > 1, ranges = [RangeCond(c1 = 3), RangeCond(c2 < 3 and c2 > 1)]
        """
        pass

    @abstractmethod
    def ndv(self, index_name: str, table_name: str, column_list: List[str]) -> int:
        """
        Estimates the number of distinct values (NDV) for specified fields within an index.

        Parameters:
            index_name (str): Name of the index.
            table_name (str): Table Name
            column_list (List[str]): List of columns(aka. fields) for which NDV is to be estimated.

        Returns:
            int: Estimated number of distinct values.

        Example:
            index_name = 'idx_videx_c1c2', table_name= 't1', field_list = ['c1', 'c2']
        """
        raise NotImplementedError()
```

### Method 2: Implement a New VIDEX-Statistic-Server

VIDEX-MySQL will request NDV and cardinality results via HTTP based on the user-specified address. Therefore, users can implement the HTTP response in any programming language.



## License

This project is dual-licensed:

- The MySQL engine implementation is licensed under GPL-2.0
- All other codes and scripts are licensed under MIT

See the [LICENSE](./LICENSES) directory for details.

## Authors
SQLBrain Group, ByteBrain, Bytedance

## Contact
If you have any questions, feel free to contact ours through email (kangrong.cn@bytedance.com, kr11thss@gmail.com).