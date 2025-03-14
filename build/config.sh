#!/usr/bin/env bash
# Global configurations
export MYSQL_HOME=/root/mysql_server
export VIDEX_HOME=/root/videx_server
export MYSQL_BUILD_DIR=$MYSQL_HOME/mysql_build_output
export MYSQL_PORT=13308
export VIDEX_PORT=5001
export LD_LIBRARY_PATH=$MYSQL_BUILD_DIR/lib64:$MYSQL_BUILD_DIR/build/plugin_output_directory:$MYSQL_BUILD_DIR/build/library_output_directory:$LD_LIBRARY_PATH
export MYSQL_LOG=/var/log/mysql.log
export VIDEX_LOG=/var/log/videx.log
