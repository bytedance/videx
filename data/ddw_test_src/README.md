# Author
Claudio
Haibo Yang
Rong Kang

# DDW Test Data Generation

This document explains how to generate and import test data for the DDW (DDL Wizard) test database.

## 1. Generate Data

Use the `generate_bulk_data.py` script to create a SQL file with test data.

```bash
python generate_bulk_data.py --sf <scale_factor> --seed <random_seed>
```

**Parameters:**

*   `--sf` (Scale Factor): An integer that determines the size of the generated data. For example, `10` generates a smaller dataset for quick tests, while `100` generates a larger one. Defaults to `100`.
*   `--seed`: An integer used to initialize the random number generator. Using the same seed ensures that the same dataset is generated every time. Defaults to `42`.

**Example:**

To generate a dataset with a scale factor of 10, run:

```bash
python generate_bulk_data.py --sf 10
```

This will create a file named `bulk_insert_data_noft_sf10.sql`.

## 2. Import Data

After generating the data, you can import it into your MySQL/MariaDB database.

**Prerequisites:**

*   You have a running MySQL/MariaDB instance.
*   You have the MySQL/MariaDB client installed.

**Commands:**

1.  **Create the database:**

    ```bash
    mysql/mariadb -h 127.0.0.1 -P 14408 -u videx -ppassword -e "create database ddw_test_src_sf10"
    ```
    *This command creates a new database. Adjust the database name to match the scale factor you used (e.g., `ddw_test_src_sf1` for `sf=1`).*

2.  **Import the schema:**

    ```bash
    mysql/mariadb -h 127.0.0.1 -P 14408 -u videx -ppassword -D ddw_test_src_sf10 < source_schema_noft.sql
    ```
    *This command creates the table structure within your new database.*

3.  **Import the data:**

    ```bash
    mysql/mariadb -h 127.0.0.1 -P 14408 -u videx -ppassword -D ddw_test_src_sf10 < bulk_insert_data_noft_sf10.sql
    ```
    *This command inserts the generated data into the tables. Make sure the `.sql` filename matches the one you generated.*