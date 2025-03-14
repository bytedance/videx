#!/usr/bin/env bash

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "${SCRIPT_DIR}/config.sh"

set -e
set -x

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

echo "Starting initialization videx..." >> $VIDEX_LOG
cd $VIDEX_HOME
python3.9 -m pip install -e . --use-pep517 >> $VIDEX_LOG
