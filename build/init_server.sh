#!/usr/bin/env bash

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "${SCRIPT_DIR}/config.sh"

set -e
set -x
# Copy configuration file
if [ -f "$SCRIPT_DIR/my.cnf" ]; then
    cp "$SCRIPT_DIR/my.cnf" "$MYSQL_BUILD_DIR/etc/my.cnf"
else
    echo "Warning: my.cnf not found!"
    exit 1
fi

[ ! -d "$MYSQL_BUILD_DIR" ] && echo "MySQL build directory not found!" && exit 1
[ ! -f "$MYSQL_BUILD_DIR/etc/my.cnf" ] && echo "my.cnf not found!" && exit 1

cd $MYSQL_BUILD_DIR

# Clean previous build if exists
if [ -d ./data ]; then
    echo "Cleaning data..."
    rm -rf ./data
fi

mkdir -p ./data
mkdir -p ./log


echo "Starting initialization process..." > $MYSQL_LOG

./build/runtime_output_directory/mysqld --defaults-file=./etc/my.cnf --initialize-insecure --user=root --basedir="$MYSQL_BUILD_DIR" --datadir=./data || exit 1


# 启动 MySQL 服务
echo "Starting MySQL server..."
./build/runtime_output_directory/mysqld --defaults-file=./etc/my.cnf --user=root --basedir="$MYSQL_BUILD_DIR" --datadir=./data --socket=./mysql_80.sock --port=$MYSQL_PORT &
MYSQL_PID=$! # 获取 MySQL 进程的 PID

# 等待 MySQL 服务启动完成
echo "Waiting for MySQL to be ready..."
for i in {1..30}; do
    ./build/runtime_output_directory/mysql -h127.0.0.1 -uroot -P$MYSQL_PORT -e "SELECT 1" && break
    sleep 2
done

# 检查 MySQL 是否启动成功
if ! ./build/runtime_output_directory/mysql -h127.0.0.1 -uroot -P$MYSQL_PORT -e "SELECT 1"; then
    echo "MySQL failed to start."
    kill $MYSQL_PID
    exit 1
fi

# 创建用户 videx
echo "Creating user videx..."
echo "CREATE USER 'videx'@'%' IDENTIFIED WITH mysql_native_password BY 'password'; GRANT ALL ON *.* TO 'videx'@'%'; FLUSH PRIVILEGES;" | \
./build/runtime_output_directory/mysql -h127.0.0.1 -uroot -P$MYSQL_PORT

if [ $? -eq 0 ]; then
    echo "User videx created successfully"
else
    echo "Failed to create user videx!"
    kill $MYSQL_PID
    exit 1
fi

# 直接杀死 MySQL 进程
echo "Shutting down MySQL server..."
kill $MYSQL_PID

# 确保进程被成功终止
for i in {1..10}; do
    if ps -p $MYSQL_PID > /dev/null; then
        echo "Waiting for MySQL to shut down..."
        sleep 1
    else
        echo "MySQL server stopped successfully."
        break
    fi
done

# 如果进程仍未停止，强制杀死
if ps -p $MYSQL_PID > /dev/null; then
    echo "MySQL did not shut down gracefully. Forcing termination..."
    kill -9 $MYSQL_PID
fi

echo "Starting initialization videx..." >> $VIDEX_LOG
cd $VIDEX_HOME
python3.9 -m pip install -e . --use-pep517 >> $VIDEX_LOG
