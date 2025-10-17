# Installation Guide for MariaDB

VIDEX supports the following installation methods:

1. Compile a complete MariaDB Server (including VIDEX engine)
2. Use Docker image installation method

## 1. Download Code

```bash
# Clone videx_server
VIDEX_HOME=$(pwd)/videx_server
MARIADB_HOME=$(pwd)/mariadb_server
git clone https://github.com/bytedance/videx.git $VIDEX_HOME

# Clone mariadb_server
git clone -b 11.8 --single-branch https://github.com/MariaDB/server.git $MARIADB_HOME
```

## 2. Prepare Environment

### 2.1 Docker Mode

If you can configure the **Clang build environment** for MariaDB without Docker, you may skip this section. Otherwise, please use Docker.

```bash
cd $VIDEX_HOME
docker build -t mariadb11_build -f build/Dockerfile.mariadb .
```

Run the following command to start the container:

```bash
docker run -dit \
  --name videx-mariadb \
  -p 2222:22 -p 13308:13308 -p 5001:5001 -p 1234:1234 \
  -v $MARIADB_HOME:/root/mariadb_server \
  -v $VIDEX_HOME:/root/videx_server \
  mariadb11_build \
  sleep infinity
```

Enter the container

```bash
docker exec -it videx-mariadb /bin/bash
```

Once inside the container, execute the script:

```bash
/root/videx_server/build/build_mariadb.sh
```

### 2.2 Non-docker Mode

You already have a local environment capable of building MariaDB. Otherwise, refer to build/Dockerfile.mariadb or use the Docker mode.

Create the build output directories
```bash
mkdir -p $MARIADB_HOME/mysql_build_output/{ccache,build,data,logs,etc,tmp}
```

Copy the VIDEX storage engine (MariaDB version) into the MariaDB source tree
```bash
cp -r $VIDEX_HOME/src/mariadb/videx $MARIADB_HOME/storage/videx
```

Copy the configuration file
```bash
cp $VIDEX_HOME/build/mariadb_my.cnf $MARIADB_HOME/mysql_build_output/etc/mariadb_my.cnf
```

### 3. CMake Build

Completely follow the official MariaDB build command, with the only difference of -DPLUGIN_VIDEX=YES.

```bash
cmake -DCMAKE_BUILD_TYPE=Debug \
  -DCMAKE_CXX_COMPILER=/usr/bin/clang++ \
  -G Ninja --fresh \
  -DCMAKE_CXX_COMPILER_LAUNCHER=ccache \
  -DCMAKE_C_COMPILER_LAUNCHER=ccache \
  -DCMAKE_INSTALL_PREFIX=. \
  -DMYSQL_DATADIR=./data \
  -DSYSCONFDIR=./etc \
  -DPLUGIN_COLUMNSTORE=NO \
  -DPLUGIN_ROCKSDB=NO \
  -DPLUGIN_S3=NO \
  -DPLUGIN_MROONGA=NO \
  -DPLUGIN_CONNECT=NO \
  -DPLUGIN_TOKUDB=NO \
  -DPLUGIN_PERFSCHEMA=NO \
  -DWITH_WSREP=OFF \
  -DPLUGIN_VIDEX=YES \
  -S $MARIADB_HOME \
  -B $MARIADB_HOME/mysql_build_output/build
```


## 4. Build and Install

```bash
cmake --build $MARIADB_HOME/mysql_build_output/build -j 10
```

## 5. Initialize the Database

Completely follow the official MariaDB build command.

```bash
cd $MARIADB_HOME/mysql_build_output/build
./scripts/mariadb-install-db \
  --srcdir=$MARIADB_HOME \
  --builddir=$MARIADB_HOME/mysql_build_output/build \
  --datadir=$MARIADB_HOME/mysql_build_output/data \
  --user=root \
  --auth-root-authentication-method=normal
```

## 6. Start MariaDB Server

Completely follow the official MariaDB build command.

```bash
cd $MARIADB_HOME/mysql_build_output/build
./sql/mariadbd \
    --defaults-file=$MARIADB_HOME/mysql_build_output/etc/mariadb_my.cnf --user=root
```

## 7. Create New User

```bash
cd $MARIADB_HOME/mysql_build_output/build
./client/mariadb -h127.0.0.1 -uroot -P13308 -e "
CREATE USER 'videx'@'%' IDENTIFIED BY 'password';
GRANT ALL ON *.* TO 'videx'@'%';
FLUSH PRIVILEGES;
"
```

## 8. Import Test Data
```bash
cd $VIDEX_HOME
mysql -h127.0.0.1 -P13308 -uvidex -ppassword -e "create database tpch_tiny;"
tar -zxf data/tpch_tiny/tpch_tiny.sql.tar.gz
mysql -h127.0.0.1 -P13308 -uvidex -ppassword -Dtpch_tiny < tpch_tiny.sql
```

## 9. Use mysql-test

You do not need to start `mariadbd` to run the VIDEX engine tests. Build the tree and use the MariaDB Test Runner (MTR).

Test suite location: `src/mariadb/videx/mysql-test/videx`

1) Build
```bash
cmake --build $MARIADB_HOME/mysql_build_output/build -j 10
```

2) Run the VIDEX suite with MTR
```bash
cd $MARIADB_HOME/mysql-test
MTR_BINDIR=$MARIADB_HOME/mysql_build_output/build \
  ./mariadb-test-run.pl --suite=videx
```

3) Run a single test
```bash
cd $MARIADB_HOME/mysql-test
MTR_BINDIR=$MARIADB_HOME/mysql_build_output/build \
  ./mariadb-test-run.pl --suite=videx --do-test=create-table-and-index
```

Optional: record expected result files on the first run
```bash
cd $MARIADB_HOME/mysql-test
MTR_BINDIR=$MARIADB_HOME/mysql_build_output/build \
  ./mariadb-test-run.pl --suite=videx --record create-table-and-index
```

Currently available tests
- `create-table-and-index`: validates VIDEX table and index creation/deletion
- `set-debug-skip-http`: verifies the server-side HTTP skip/disable path
