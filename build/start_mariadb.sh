#!/bin/bash

echo "MARIADB-START..." >> /var/log/mariadb.log
cd /root/mariadb_server/mysql_build_output/build
./sql/mariadbd \
    --defaults-file=/root/mariadb_server/mysql_build_output/etc/mariadb_my.cnf \
    --user=root >> /var/log/mariadb.log 2>&1 &

echo "SERVER-START..." >> /var/log/videx.log
cd /root/videx_server

echo "Starting Videx server..." >> /var/log/videx.log
python3.9 src/sub_platforms/sql_opt/videx/scripts/start_videx_server.py --port 5001 >> /var/log/videx.log 2>&1 &

tail -f /var/log/videx.log