
This document outlines the known limitations of VIDEX. The primary goal of VIDEX is to simulate the MySQL/MariaDB optimizer's behavior for "what-if" index analysis. Its accuracy depends on simulating the database's internal cost models and using statistical metadata.

**Important**: Due to the inherent complexity of database systems, many edge cases remain untested. This list is not exhaustive. We strongly encourage users to test VIDEX's behavior in their own environments and welcome contributions and issue reports for any discrepancies found.

### 1. Feature Coverage Limitations

This section details the database features that VIDEX does not support or has not been fully tested.

#### Unsupported or Insufficiently Tested Data Types
- **Unsupported**: VIDEX may not correctly handle tables containing the following data types:
  - `BLOB` and `TEXT` families (`BLOB`, `MEDIUMBLOB`, `LONGBLOB`, `TEXT`, `MEDIUMTEXT`, `LONGTEXT`). (See Issue #66)
  - `JSON` data type.
- **Insufficiently Tested**: The following data types have not been thoroughly tested and may lead to unexpected behavior:
  - **For MySQL 8+**: `BIT`, `YEAR`, `TIME`, `SET`, and Spatial Data Types (`GEOMETRY`, `POINT`, etc.).
  - **For MariaDB 11.8+**: `BIT`, `INET4`/`INET6`, `SERIAL`, `ROW TYPE OF`, `TYPE OF`, `SQL_TSI_YEAR`, `YEAR`, `TIME`.

#### Unsupported Index Types
- **Functional Indexes**: Currently not supported, though under internal testing. (See Issue #66)
- **FULL-TEXT Indexes**: Currently not supported, though under internal testing.
- **Spatial Indexes**.
- **Multi-valued Indexes** (MySQL 8+).
- Cost simulation for equality lookups on **Primary Keys (PK)** and **Unique Keys (UK)** has known issues. (See Issue #67)

#### Unsupported SQL Features and Statements
- **`EXPLAIN` Only**: VIDEX is designed to work with `EXPLAIN` statements. It does not support `EXPLAIN ANALYZE`, as `ANALYZE` involves actual query execution, which is outside VIDEX's simulation scope.
- **Single-Row Subqueries**: May not be simulated correctly in all cases. (See Issue #68)

#### Untested Table and Column Features
- **Table Structures**: Features like **Partitioned Tables**, **Temporary Tables**, and **Sequences** have not been sufficiently tested.
- **Column Operations**: While `ADD/DROP INDEX` is fully supported, the impact of other `ALTER TABLE` operations like adding or dropping columns has not been fully tested.

### 2. Statistics & Cost Model Accuracy Limitations

VIDEX's accuracy is fundamentally tied to the quality of its statistical metadata and its ability to capture the joint distributions of multiple columns.

- **Multi-Column NDV Estimation**: VIDEX only collects multi-column NDV (Number of Distinct Values) statistics for existing composite indexes. For other column combinations, it defaults to the independence assumption, which often overestimates the true NDV for correlated data.
- **Multi-Column Cardinality Estimation**: Similarly, cardinality estimation for predicates on multiple columns defaults to the independence assumption, which can lead to an underestimation of selectivity (and thus, cardinality) for correlated data.
- **`pct_cached` Variability**: The `pct_cached` parameter, which estimates the percentage of an index residing in the buffer pool, is highly dynamic in a live production environment. VIDEX's simulation of this value is a simplification and may not reflect the real-time state of the cache.
- **Dependency on AI Models**: If you integrate a custom AI model for NDV and cardinality estimation, the accuracy of VIDEX's predictions becomes entirely dependent on the performance and accuracy of that model.
- **Deviation from InnoDB's Estimation**: In some cases, particularly for range queries, InnoDB's own cardinality estimates can be significantly inaccurate. VIDEX, by using more precise statistics (like histograms), may produce estimates closer to the ground truth. This can result in VIDEX generating a *different but potentially better* query plan than the one produced on the actual InnoDB instance. While VIDEX is more 'correct' in this scenario, it deviates from its goal of perfectly mimicking the original optimizer's behavior. (See Issue #5)

### 3. AI Model Limitations

**Unverified AI Models**: While AI models (PLM4NDV, AdaNDV) have been integrated (see #46, #48), they lack comprehensive validation on benchmarks like TPC-H and JOB. Additionally, the model training pipelines are not included in this repository, necessitating further documentation and testing for user adoption.


### 4. Data Collection and Performance Limitations

- **Performance Impact of Default Collection**: The default metadata collection scripts can impact production database performance, although collection operations (NDV and histogram) are run at most once per column.
- **Sampling-based Metadata Collection**: This feature, introduced in #48, has not been fully tested and requires further validation on benchmarks like TPC-H and JOB. (See Issue #69)
- **Stale Statistics**: VIDEX does not automatically refresh statistics. The collected metadata can become stale if the underlying data changes significantly, leading to inaccurate plan simulations.

### 5. Concurrency and Execution Environment Limitations

VIDEX's scope is limited to simulating the query optimizer's planning phase. It does not simulate the actual query execution environment.

- **Single-Query Focus**: VIDEX is designed to simulate a single query in isolation. It does not account for runtime behaviors or database features like:
  - **Triggers**
  - **Stored Procedures and Functions**
  - **Transactions** and their isolation levels
  - **Locking and concurrency effects**
- **Views**: Support for `VIEW`s has undergone limited testing and is not guaranteed to be fully stable or accurate in all scenarios.

### 6. Version Compatibility Limitations

- VIDEX has been primarily tested on **MySQL 8.0**, **MySQL 5.7**, and **MariaDB 11.8**. While it may function on other patch versions, compatibility is not guaranteed.
- For a detailed support matrix, please refer to the `Version Support` section in the main `README.md`.

### Known Bugs

For a list of currently open bugs and known issues, please consult our GitHub Issues page, filtered by the "Bug" label:

[https://github.com/bytedance/videx/issues?q=is%3Aissue+is%3Aopen+label%3ABug](https://github.com/bytedance/videx/issues?q=is%3Aissue+is%3Aopen+label%3ABug)