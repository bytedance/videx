echo "CMAKE..."
/usr/bin/cmake \
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

echo "CMAKE BUILD..."
/usr/bin/cmake --build /root/mariadb_server/mysql_build_output/build -j 10

echo "MARIADB-INSTALL-DB..."
cd /root/mariadb_server/mysql_build_output/build
./scripts/mariadb-install-db \
  --srcdir=/root/mariadb_server \
  --builddir=/root/mariadb_server/mysql_build_output/build \
  --datadir=/root/mariadb_server/mysql_build_output/data \
  --user=root \
  --auth-root-authentication-method=normal

echo "MARIADB-START..."
cd /root/mariadb_server/mysql_build_output/build
./sql/mariadbd \
    --defaults-file=/root/mariadb_server/mysql_build_output/etc/mariadb_my.cnf \
    --user=root >> /var/log/mysql.log 2>&1 &
    MARIADB_PID=$!

echo "Waiting for MariaDB server to start..."
for i in {1..30}; do
    if ./client/mariadb -h127.0.0.1 -uroot -P13308 -e "SELECT 1;" > /dev/null 2>&1; then
        echo "Server is ready!"
        break
    fi
    echo "Waiting... ($i/30)"
    sleep 2
done

if ! ./client/mariadb -h127.0.0.1 -uroot -P13308 -e "SELECT 1;" > /dev/null 2>&1; then
    echo "Error: MariaDB server is not responding!"
    echo "Checking logs..."
    tail -n 20 /var/log/mysql.log
    kill $MARIADB_PID
    exit 1
fi

echo "Setting up database users..."
./client/mariadb -h127.0.0.1 -uroot -P13308 -e "
CREATE USER IF NOT EXISTS 'videx'@'%' IDENTIFIED BY 'password';
GRANT ALL PRIVILEGES ON *.* TO 'videx'@'%';
FLUSH PRIVILEGES;
"

echo "Shutting down MariaDB server..."
kill $MARIADB_PID

for i in {1..10}; do
    if ps -p $MARIADB_PID > /dev/null; then
        echo "Waiting for MariaDB to shut down..."
        sleep 1
    else
        echo "MariaDB server stopped successfully."
        break
    fi
done

if ps -p $MARIADB_PID > /dev/null; then
    echo "MariaDB did not shut down gracefully. Forcing termination..."
    kill -9 $MARIADB_PID
fi