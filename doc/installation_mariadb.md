# Installation Guide for MariaDB

VIDEX supports the following installation methods:

1. Compile a complete MariaDB Server (including VIDEX engine)
2. Use Docker image installation method

## 1. Prepare Environment

### 1.1 Download Code

```bash
# Clone videx_server
VIDEX_HOME=$(pwd)/videx_server
MARIADB_HOME=$(pwd)/mariadb_server
git clone -b adapt2mariadb-11.8 --single-branch https://github.com/YoungHypo/videx.git $VIDEX_HOME

# Clone mariadb_server
git clone -b videx-temp --single-branch https://github.com/YoungHypo/server.git $MARIADB_HOME
```

### 1.2 Build Docker Image
If you can configure the **Clang build environment** for MariaDB without Docker, you may skip to the next section.  
Otherwise, please use Docker.

```bash
cd $VIDEX_HOME
docker build -t mariadb11_build -f build/Dockerfile.mariadb .
```

### 1.3 Start Docker Container

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

### 1.4 Enter the Container

```bash
docker exec -it videx-mariadb /bin/bash
```

Once inside the container, execute the script:

```bash
./root/videx_server/build/build_mariadb.sh
```

## 2. CMake Build

```bash
/usr/bin/cmake -DCMAKE_BUILD_TYPE=Debug \
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
  -S /root/mariadb_server \
  -B /root/mariadb_server/mysql_build_output/build
```


## 3. Build and Install

```bash
/usr/bin/cmake --build /root/mariadb_server/mysql_build_output/build -j 10
```

### 4. Initialize the Database

```bash
cd /root/mariadb_server/mysql_build_output/build
./scripts/mariadb-install-db \
  --srcdir=/root/mariadb_server \
  --builddir=/root/mariadb_server/mysql_build_output/build \
  --datadir=/root/mariadb_server/mysql_build_output/data \
  --user=root \
  --auth-root-authentication-method=normal
```

## 5. Start MariaDB Server

```bash
cd /root/mariadb_server/mysql_build_output/build
./sql/mariadbd \
    --defaults-file=/root/mariadb_server/mysql_build_output/etc/mariadb_my.cnf --user=root
```

## 6. Create New User

```bash
cd /root/mariadb_server/mysql_build_output/build
./client/mariadb -h127.0.0.1 -uroot -P13308 -e "
CREATE USER 'videx'@'%' IDENTIFIED BY 'password';
GRANT ALL ON *.* TO 'videx'@'%';
FLUSH PRIVILEGES;
"
```

## 7. Import Test Data
```bash
cd $VIDEX_HOME
mysql -h127.0.0.1 -P13308 -uvidex -ppassword -e "create database tpch_tiny;"
tar -zxf data/tpch_tiny/tpch_tiny.sql.tar.gz
mysql -h127.0.0.1 -P13308 -uvidex -ppassword -Dtpch_tiny < tpch_tiny.sql
```

## Use mysql-test

You do not need to start `mariadbd` to run the VIDEX engine tests. Build the tree and use the MariaDB Test Runner (MTR).

Test suite location: `src/mariadb/videx/mysql-test/videx`

1) Build
```bash
/usr/bin/cmake --build /root/mariadb_server/mysql_build_output/build -j 10
```

2) Run the VIDEX suite with MTR
```bash
cd /root/mariadb_server/mysql-test
MTR_BINDIR=/root/mariadb_server/mysql_build_output/build \
  ./mariadb-test-run.pl --suite=videx
```

3) Run a single test
```bash
cd /root/mariadb_server/mysql-test
MTR_BINDIR=/root/mariadb_server/mysql_build_output/build \
  ./mariadb-test-run.pl --suite=videx --do-test=create-table-and-index
```

Optional: record expected result files on the first run
```bash
cd /root/mariadb_server/mysql-test
MTR_BINDIR=/root/mariadb_server/mysql_build_output/build \
  ./mariadb-test-run.pl --suite=videx --record create-table-and-index
```

Currently available tests
- `create-table-and-index`: validates VIDEX table and index creation/deletion
- `set-debug-skip-http`: verifies the server-side HTTP skip/disable path
