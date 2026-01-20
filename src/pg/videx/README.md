### Videx For Postgresql

Videx-for-pg is developing in the form of a PostgreSQL plugin...

[done] run with videx-statistic-server, support fetch all statistic except pg-statistic-ext
[wip] support e2e card injection during optimizing

---

### How It Works

1. Where is the statistical information stored?
   
   Postgres stores statistical information in the following system tables：

	- pg_class
	- pg_statistic
	- pg_statistic_ext


2. How does the optimizer obtain statistics?

	postgres fetch statistics for relations depends on three core function:

	- get_relation_stats: access pg_statistic_ext,pg_statistic
	- get_index_stats: access pg_statistic_ext,pg_statistic
	- relation_estimate_size:  access pg_class
  


videx-for-postgres fetch statistic from system tables and upload them to videx-statistic-server. At the same time, use a hook method to make the statistics retrieval function prioritize obtaining statistics from the videx-statistic-server.

### Quick Start With Videx-Statistic-Server

#### step1: install postgresql from source code

1. fetch source code of postgresql from [https://www.postgresql.org/ftp/source/v17.5/ ](https://www.postgresql.org/ftp/source/v17.5/)
2. build from source code (MAKR: you should replace ***target_dir*** and ***data_dir*** with your local path)

```bash
cd postgresql-17.5
./configure --prefix={target_dir} --enable-debug

make && make install

cd {target_dir}/bin
./initdb -U postgres -d {data_dir}
```

3. Set environment variable

```
export PATH={target_dir}/bin:$PATH
export LD_LIBRARY_PATH={target_dir}/lib:$LD_LIBRARY_PATH
```

---

#### step2: compile videx

1. Copy the pg/videx folder to the contrib folder (plugin dir for pg) in your pg directory

```bash
cp -rf videx/src/pg/videx postgresql-17.5/contrib/
```

2. go into postgresql17.5/contrib/videx:

```bash
make && make install
```

#### step3: Configure and start postgresql server

Edit postgresql.conf  in {data_dir}，set shared_preload_libraries as videx, then postgresql while load videx.so while starting:

```SQL
shared_preload_libraries = 'videx' # (change requires restart)`
```

we assume no password is set:

```SQL
{target_dir}/bin/postgres -D {data_dir} -p 55555
```


---

#### step4：register videx in pg

connect postgres with psql (connect to database: postgres defaultly, we can create another databases this database):

```SQL
{target_dir}/bin/psql -U postgres -p 55555
```

you can also directly install postgresql-client, then you can use psql under any directory:

```BASH
sudo apt install -y postgresql-client // for ubuntu
```


---

#### step3: use videx

1. create source database and create extension

```SQL
-- connect to database postgres and create database:test
create database test;
-- switch to database:test
\c test
-- register extension videx on database:test
create extension videx;
```

verify if the registration was successful

```sql
test=# SELECT * FROM pg_extension WHERE extname = 'videx';
oid   | extname | extowner | extnamespace | extrelocatable | extversion | extconfig | extcondition 
--------+---------+----------+--------------+----------------+------------+-----------+--------------
368789 | videx   |       10 |         2200 | t              | 1.0        |           | 
(1 row)
```

2. start pg-statistic-sever

```bash
python3 src/sub_platforms/sql_opt/videx/scripts/start_videx_server.py
```

3. collect and import videx metadata

```bash
python3 src/sub_platforms/sql_opt/videx/scripts/videx_build_env_pg.py \
--target 127.0.0.1:55555:test:postgres:passwd \
--videx 127.0.0.1:55555:videx_test:postgres:passwd
```

4. connect to database: videx_test and run explain.

```bash
psql -U postgres -p 55555 -d videx_test
```