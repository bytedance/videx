#!/usr/bin/env bash
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "${SCRIPT_DIR}/config.sh"

# Error handling
set -e  # Exit on error
set -x  # Print commands for debugging

# Start SSH service
/etc/init.d/ssh restart

# Copy videx to storage
if [ -d "$MYSQL_HOME/storage/videx" ]; then
    echo "Videx directory already exists. Skipping copy."
else
    echo "Copying videx to $MYSQL_HOME/storage..."
    cp -r "$VIDEX_HOME/src/mysql/videx" "$MYSQL_HOME/storage"
fi

BOOST_DIR=$MYSQL_HOME/boost

# Create necessary directories
mkdir -p "$BOOST_DIR"
mkdir -p "$MYSQL_BUILD_DIR"/{etc,build,lib64,data,log}

# Copy my.cnf to build directory
if [ -f "$SCRIPT_DIR/my.cnf" ]; then
    cp "$SCRIPT_DIR/my.cnf" "$MYSQL_BUILD_DIR/etc/my.cnf"
else
    echo "Warning: my.cnf not found!"
    exit 1
fi
