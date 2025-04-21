

# VIDEX

<p align="center">
  <a href="./README.md">English</a> |
  <a href="./README_zh.md">简体中文</a>
</p>

<p align="center">
  <a href="https://www.youtube.com/watch?v=Cm5O61kXQ_c">
    <img src="https://img.shields.io/badge/Watch-Demo-red?style=for-the-badge&logo=youtube" alt="Watch Demo"/>
  </a>
  <a href="https://hub.docker.com/repository/docker/kangrongme/videx">
    <img src="https://img.shields.io/docker/pulls/kangrongme/videx?style=for-the-badge&logo=docker" alt="Docker Pulls"/>
  </a>
</p>

**VIDEX**: The Disaggregated, Extensible **\[VI\]**rtual in**\[DEX\]** Engine for What-If Analysis in MySQL 🚀
- **Virtual Index**: Does not require real data, relies only on statistical information and algorithm models to accurately simulate MySQL query plans, table join orders, and index selections;
- **Disaggregated**: VIDEX runs on a standalone instance without affecting production MySQL. Furthermore, the Statistic Server (optionally AI-enhanced to provide cardinality and ndv) can be deployed separately, enabling GPU-heterogeneous computing and seamless hot-updates.
- **Extensible**: VIDEX offers convenient interfaces allowing users to apply models like `cardinality` and `ndv` to downstream MySQL tasks (e.g., index recommendation);

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
We expect that VIDEX can provide users with a better platform to more easily test the effectiveness of cardinality and NDV algorithms, and apply them on SQL optimization tasks. VIDEX has been deployed in Bytedance production environment, serving large-scale slow SQL optimizations. 

---


## 1. Overview

<p align="center">
  <img src="doc/videx-structure.png" width="600">
</p>

VIDEX consists of two parts:

- **VIDEX-Optimizer-Plugin** (abbr. **VIDEX-Optimizer**): Conducted a thorough review of over 90 interface functions in the MySQL handler, and implement the index-related parts.
- **VIDEX-Statistic-Server** (abbr. **VIDEX-Statistic**): The cost estimation service calculates NDV and Cardinality based on collected statistical information and estimation algorithms, and returns the results to the VIDEX-Optimizer instance. 

VIDEX creates an individual virtual database according to the specified target database in the raw instance,
containing a series of tables with the same DDL, but replacing the engine from `InnoDB` to `VIDEX`.

## 2 Quick Start

### 2.1 Install Python Environment

VIDEX requires Python 3.9 for metadata collection tasks. We recommend using Anaconda/Miniconda to create an isolated Python environment:

**For Linux/macOS Users：**
```bash
# Clone repository
VIDEX_HOME=videx_server
git clone git@github.com:bytedance/videx.git $VIDEX_HOME
cd $VIDEX_HOME

# Create and activate Python environment
conda create -n videx_py39 python=3.9
conda activate videx_py39

# Install VIDEX
python3.9 -m pip install -e . --use-pep517
```

**For Windows Users：**
```cmd
# Clone repository, Git must be pre-installed
set VIDEX_HOME=videx_server
git clone git@github.com:bytedance/videx.git %VIDEX_HOME%
cd %VIDEX_HOME%

# Create and activate Python environment
conda create -n videx_py39 python=3.9
conda activate videx_py39

# Install VIDEX
python -m pip install -e . --use-pep517 
```

### 2.2 Launch VIDEX (Docker Mode)

For simplified deployment, we provide pre-built Docker images containing:
- VIDEX-Optimizer: Based on [Percona-MySQL 8.0.34-26](https://github.com/percona/percona-server/tree/release-8.0.34-26) with integrated VIDEX plugin
- VIDEX-Server: NDV and cardinality algorithm service

#### Install Docker
If you haven't installed Docker yet:
- [Docker Desktop for Windows/Mac](https://www.docker.com/products/docker-desktop/)
- Linux: Follow the [official installation guide](https://docs.docker.com/engine/install/)

#### Launch VIDEX Container
```bash
docker run -d -p 13308:13308 -p 5001:5001 --name videx kangrongme/videx:0.0.2
```

> **Alternative Deployment Options**
>
> VIDEX also supports the following deployment methods, see [Installation Guide](doc/installation.md):
> - Build complete MySQL Server from source
> - Build VIDEX plugin only and install on existing MySQL
> - Deploy VIDEX-Server independently (supports custom optimization algorithms)

## 3 Examples

### 3.1 TPCH-Tiny Example

This example demonstrates the complete VIDEX workflow using the `TPC-H Tiny` dataset (1% random sample from TPC-H sf1).

#### Environment Details

The example assumes all components are deployed locally via Docker:

Component | Connection Info
---|---
Target-MySQL (Production DB) | 127.0.0.1:13308, username:videx, password:password  
VIDEX-Optimizer (Plugin) | Same as Target-MySQL
VIDEX-Server | 127.0.0.1:5001

#### Step 1: Import Test Data

**For Linux/macOS Users：**
```bash
cd $VIDEX_HOME

# Create database (If you don't have the MySQL client installed on your machine, you need to download and install MySQL. After installation, do not start the MySQL server, as VIDEX will use the IP and port.)
mysql -h127.0.0.1 -P13308 -uvidex -ppassword -e "create database tpch_tiny;"

# Import data
tar -zxf data/tpch_tiny/tpch_tiny.sql.tar.gz
mysql -h127.0.0.1 -P13308 -uvidex -ppassword -Dtpch_tiny < tpch_tiny.sql
```

**For Windows Uesrs：**
```cmd
# Change to project directory (assuming VIDEX_HOME environment variable is set)
cd %VIDEX_HOME%
# Download test data

# Create database
mysql -h127.0.0.1 -P13308 -uvidex -ppassword -e "create database tpch_tiny;"

# Import data
tar -zxf data/tpch_tiny/tpch_tiny.sql.tar.gz
mysql -h127.0.0.1 -P13308 -uvidex -ppassword -Dtpch_tiny < tpch_tiny.sql
```

#### Step 2: Collect and Import VIDEX Metadata

Ensure VIDEX environment is installed. If not, refer to [2.1 Install Python Environment](#21-install-python-environment).

**For Linux/macOS Users:**
```shell
cd $VIDEX_HOME
python src/sub_platforms/sql_opt/videx/scripts/videx_build_env.py \
 --target 127.0.0.1:13308:tpch_tiny:videx:password \
 --videx 127.0.0.1:13308:videx_tpch_tiny:videx:password
```

**For Windows Users:**
```cmd
cd %VIDEX_HOME%
# Windows CMD doesn't support \ as line continuation, parameters must be in the same line
python src/sub_platforms/sql_opt/videx/scripts/videx_build_env.py --target "127.0.0.1:13308:tpch_tiny:videx:password" --videx "127.0.0.1:13308:videx_tpch_tiny:videx:password"
```

Output:
```log
2025-02-17 13:46:48 [2855595:140670043553408] INFO     root            [videx_build_env.py:178] - Build env finished. Your VIDEX server is 127.0.0.1:5001.
You are running in non-task mode.
To use VIDEX, please set the following variable before explaining your SQL:
--------------------
-- Connect VIDEX-Optimizer: mysql -h127.0.0.1 -P13308 -uvidex -ppassword -Dvidex_tpch_tiny
USE videx_tpch_tiny;
SET @VIDEX_SERVER='127.0.0.1:5001';
-- EXPLAIN YOUR_SQL;
```

Metadata is now collected and imported to VIDEX-Server. The JSON file is written to `videx_metadata_tpch_tiny.json`.

If users have prepared metadata files, they can specify `--meta_path` to skip collection and import directly.

#### Step 3: EXPLAIN SQL

Connect to `VIDEX-Optimizer` and execute EXPLAIN.

To demonstrate VIDEX's effectiveness, we compare EXPLAIN details for TPC-H Q21, a complex query with four-table joins involving `WHERE`, `aggregation`, `ORDER BY`, `GROUP BY`, `EXISTS` and `self-joins`. MySQL can choose from 11 indexes across 4 tables.

Since VIDEX-Server is deployed on the VIDEX-Optimizer node with default port (5001), we don't need to set `VIDEX_SERVER` additionally.
If VIDEX-Server is deployed elsewhere, execute `SET @VIDEX_SERVER` first.

```sql
-- SET @VIDEX_SERVER='127.0.0.1:5001'; -- Not needed for Docker deployment
-- Connect VIDEX-Optimizer: mysql -h127.0.0.1 -P13308 -uvidex -ppassword -Dvidex_tpch_tiny
-- USE videx_tpch_tiny;
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

We compare VIDEX and InnoDB. We use `EXPLAIN FORMAT=JSON`, a more strict format.
We compare not only table join order and index selection but every detail of query plans (e.g., rows and cost at each step).

As shown below, VIDEX (left) generates a query plan almost 100% identical to InnoDB (right).
Complete EXPLAIN results are in `data/tpch_tiny`.

![explain_tpch_tiny_compare.png](doc/explain_tpch_tiny_compare.png)

Note that VIDEX accuracy depends on three key algorithm interfaces:
- `ndv`
- `cardinality`
- `pct_cached` (percentage of index data loaded in memory). Can be set to 0 (cold start) or 1 (hot data) if unknown, but production instances' `pct_cached` may vary constantly.

A key VIDEX function is simulating index costs. We add an extra index. VIDEX's index addition cost is `O(1)`:

```sql
ALTER TABLE tpch_tiny.orders ADD INDEX idx_o_orderstatus (o_orderstatus);
ALTER TABLE videx_tpch_tiny.orders ADD INDEX idx_o_orderstatus (o_orderstatus);
```

Re-running EXPLAIN shows MySQL-InnoDB and VIDEX query plans changed identically, both adopting the new index.

[//]: # (![explain_tpch_tiny_compare_alter_index.png]&#40;doc/explain_tpch_tiny_compare_alter_index.png&#41;)
![explain_tpch_tiny_compare_alter_index.png](doc/explain_tpch_tiny_compare_alter_index.png)

> VIDEX's row estimate (7404) differs from MySQL-InnoDB (7362) by ~0.56%, due to cardinality estimation algorithm error.

Finally, we remove the index:

```sql
ALTER TABLE tpch_tiny.orders DROP INDEX idx_o_orderstatus;
ALTER TABLE videx_tpch_tiny.orders DROP INDEX idx_o_orderstatus;
```

### 3.2 TPCH sf1 (1g) Example

We provide metadata file for TPC-H sf1: `data/videx_metadata_tpch_sf1.json`, allowing direct import without collection.

**For Linux/macOS Users:**
```shell
cd $VIDEX_HOME
python src/sub_platforms/sql_opt/videx/scripts/videx_build_env.py \
 --target 127.0.0.1:13308:tpch_sf1:user:password \
 --meta_path data/tpch_sf1/videx_metadata_tpch_sf1.json

```

**For Windows Users:**
```cmd
cd %VIDEX_HOME%
python src/sub_platforms/sql_opt/videx/scripts/videx_build_env.py --target 127.0.0.1:13308:tpch_sf1:user:password --meta_path data/tpch_sf1/videx_metadata_tpch_sf1.json
```

Like TPCH-tiny, VIDEX generates nearly identical query plans to InnoDB for `TPCH-sf1 Q21`, see `data/tpch_sf1`.

![explain_tpch_sf1_compare.png](doc/explain_tpch_sf1_compare.png)

## 4. API

Specify connection methods for original database and videx-stats-server. Collect statistics from original database, save to intermediate file, then import to VIDEX database.

> - If VIDEX-Optimizer starts separately rather than installing plugin on target-MySQL, users can specify `VIDEX-Optimizer` address via `--videx`
> - If VIDEX-Server starts separately rather than deploying on VIDEX-Optimizer machine, users can specify `VIDEX-Server` address via `--videx_server`
> - If users have generated metadata file, specify `--meta_path` to skip collection

Command example:

```bash
cd $VIDEX_HOME/src/sub_platforms/sql_opt/videx/scripts
python videx_build_env.py --target 127.0.0.1:13308:tpch_tiny:videx:password \
[--videx 127.0.0.1:13309:videx_tpch_tiny:videx:password] \
[--videx_server 127.0.0.1:5001] \
[--meta_path /path/to/file]
```

## 5. 🚀Integrate Your Custom Model🚀

### Method 1: Add into VIDEX-Statistic-Server

Users can fully implement `VidexModelBase`.

If users focus on cardinality and ndv (two popular research topics), 
they can also inherit from `VidexModelInnoDB` (see `VidexModelExample`).
`VidexModelInnoDB` abstracts away complexities such as system variables 
and index metadata formats, providing a basic (heuristic) algorithm for ndv and cardinality.

```python
class VidexModelBase(ABC):
    """
    Abstract cost model class. VIDEX-Statistic-Server receives requests from VIDEX-Optimizer for Cardinality
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

VIDEX-Optimizer will request NDV and cardinality results via HTTP based on the user-specified address. Therefore, users can implement the HTTP response in any programming language.



## License

This project is dual-licensed:

- The MySQL engine implementation is licensed under GPL-2.0
- All other codes and scripts are licensed under MIT

See the [LICENSE](./LICENSES) directory for details.

## Paper Citation

If you find this code useful, we would appreciate citations to our paper:

```
@misc{kang2025videx,
      title={VIDEX: A Disaggregated and Extensible Virtual Index for the Cloud and AI Era}, 
      author={Rong Kang and Shuai Wang and Tieying Zhang and Xianghong Xu and Linhui Xu and Zhimin Liang and Lei Zhang and Rui Shi and Jianjun Chen},
      year={2025},
      eprint={2503.23776},
      archivePrefix={arXiv},
      primaryClass={cs.DB},
      url={https://arxiv.org/abs/2503.23776}, 
}
```

## Authors
ByteBrain Team, Bytedance

## Contact
If you have any questions, feel free to contact us:
Rong Kang: kangrong.cn@bytedance.com, kr11thss@gmail.com, 
Tieying Zhang: tieying.zhang@bytedance.com
