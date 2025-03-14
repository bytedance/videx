#!/usr/bin/env bash
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "${SCRIPT_DIR}/config.sh"


# Unset proxy environment variables to avoid interference
unset http_proxy HTTP_PROXY
unset https_proxy HTTPS_PROXY
unset no_proxy NO_PROXY
unset all_proxy ALL_PROXY
unset ftp_proxy FTP_PROXY

cd $MYSQL_BUILD_DIR
echo "Starting MySQL..." >> $MYSQL_LOG
build/runtime_output_directory/mysqld --defaults-file=$MYSQL_BUILD_DIR/etc/my.cnf  --user=root --basedir=$MYSQL_BUILD_DIR --datadir=$MYSQL_BUILD_DIR/data >> $MYSQL_LOG 2>&1 &

echo "Starting videx_server..." >> $VIDEX_LOG

echo $VIDEX_HOME/src/sub_platforms/sql_opt/videx/scripts
cd $VIDEX_HOME/src/sub_platforms/sql_opt/videx/scripts
echo "Starting Videx server on port 5001..." >> $VIDEX_LOG
python3.9 start_videx_server.py --port 5001 >> $VIDEX_LOG 2>&1 &

tail -f $VIDEX_LOG