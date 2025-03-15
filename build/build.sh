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

# Clean previous build if exists
if [ -d "$MYSQL_BUILD_DIR" ]; then
    echo "Cleaning previous build directory..."
    rm -rf "$MYSQL_BUILD_DIR"
fi

# Create necessary directories
mkdir -p "$BOOST_DIR"
mkdir -p "$MYSQL_BUILD_DIR"/{etc,build,lib64}

# Change to MySQL source directory
cd "$MYSQL_BUILD_DIR"

# Configure MySQL build with CMake
# -DWITH_DEBUG=OFF: Disable debug build
# -DCMAKE_BUILD_TYPE=Release: Build release version
# -DBUILD_CONFIG=mysql_release: Use release configuration
# -DFEATURE_SET=community: Build community edition
# -DCMAKE_INSTALL_PREFIX: Set installation directory
# -DMYSQL_DATADIR: Set data directory
# -DSYSCONFDIR: Set configuration directory
# -DWITH_BOOST: Specify boost directory
# -DDOWNLOAD_BOOST: Automatically download boost if needed
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
    -DWITH_VIDEX_STORAGE_ENGINE=1

# Build MySQL server (mysqld)
echo "Building MySQL server..."
cmake --build build --target mysqld -- -j "$(nproc)"

# Build MySQL client
echo "Building MySQL client..."
cmake --build build --target mysql -- -j "$(nproc)"

# build videx
cmake --build build --target videx -- -j "$(nproc)"

# Check if build was successful
if [ ! -f "build/runtime_output_directory/mysqld" ]; then
    echo "Error: MySQL server build failed!"
    exit 1
fi

if [ ! -f "build/runtime_output_directory/mysql" ]; then
    echo "Error: MySQL client build failed!"
    exit 1
fi

# Copy necessary libraries and scripts
echo "Copying libraries and scripts..."
# cp /usr/local/gcc-9.3.0/lib64/* "$MYSQL_BUILD_DIR/lib64/"
# cp ../build/scripts/* "$MYSQL_BUILD_DIR/"

# Add MySQL and mysqld to PATH environment variable
echo "Adding MySQL client and server to PATH..."
MYSQL_BIN_DIR="$MYSQL_BUILD_DIR/build/runtime_output_directory/"

if [ -d "$MYSQL_BIN_DIR" ]; then
    export PATH="$MYSQL_BIN_DIR:$PATH"
    echo "export PATH=\"$MYSQL_BIN_DIR:\$PATH\"" >> ~/.bashrc
    echo "MySQL binaries added to PATH. Please restart your shell or run 'source ~/.bashrc' to apply."
else
    echo "Error: MySQL binary directory not found! Ensure the build was successful."
    exit 1
fi

echo "MySQL build completed successfully!"
echo "Build directory: $MYSQL_BUILD_DIR"