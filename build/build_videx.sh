#!/usr/bin/env bash
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "${SCRIPT_DIR}/config.sh"

# Error handling
set -e  # Exit on error
set -x  # Print commands for debugging

if [ -d "$MYSQL_HOME/storage/videx" ]; then
    echo "Deleting existing $MYSQL_HOME/storage/videx directory..."
    rm -rf "$MYSQL_HOME/storage/videx"
fi

echo "Copying $VIDEX_HOME/src/mysql/videx to $MYSQL_HOME/storage..."
cp -r "$VIDEX_HOME/src/mysql/videx" "$MYSQL_HOME/storage"

BOOST_DIR=$MYSQL_HOME/boost

# Clean previous build
if [ -d "$MYSQL_BUILD_DIR" ]; then
    echo "Cleaning previous build directory..."
    rm -rf "$MYSQL_BUILD_DIR"
fi

# Create necessary directories
mkdir -p "$BOOST_DIR"
mkdir -p "$MYSQL_BUILD_DIR"/{etc,build,lib64}

# Change to MySQL source directory
cd "$MYSQL_BUILD_DIR"


cmake .. \
    -B./build \
    -DWITH_DEBUG=OFF \
    -DCMAKE_BUILD_TYPE=Release \
    -DBUILD_CONFIG=mysql_release \
    -DFEATURE_SET=community \
    -DCMAKE_INSTALL_PREFIX=. \
    -DMYSQL_DATADIR=./data \
    -DSYSCONFDIR=./etc \
    -DWITH_BOOST="$BOOST_DIR" \
    -DDOWNLOAD_BOOST=ON \
    -DWITH_ROCKSDB=OFF \
    -DDOWNLOAD_BOOST_TIMEOUT=3600 \
    -DWITH_VIDEX_STORAGE_ENGINE=1 \
    -DPLUGIN_VIDEX=DYNAMIC

echo "Building MySQL server..."
cmake --build build --target videx -- -j "$(nproc)"
