#!/usr/bin/env bash
set -e
set -x

/etc/init.d/ssh restart

git config --global --add safe.directory /root/mariadb_server

mkdir -p /root/mariadb_server/mysql_build_output/{ccache,build,data,logs,etc,tmp}

export CCACHE_DIR=/root/mariadb_server/mysql_build_output/ccache

if [ -d /root/mariadb_server/storage/videx ]; then
    echo "Videx directory already exists. Skipping copy."
else
    echo "Copying videx to mariadb_server..."
    cp -r /root/videx_server/src/mysql/videx /root/mariadb_server/storage/videx
fi

if [ -f /root/mariadb_server/mysql_build_output/etc/my.cnf ]; then
    echo "my.cnf already exists. Skipping copy."
else
    if [ -f /root/videx_server/build/my.cnf ]; then
        echo "Copying my.cnf to mariadb_server..."
        cp /root/videx_server/build/my.cnf /root/mariadb_server/mysql_build_output/etc/my.cnf
    else
        echo "Source my.cnf not found!"
        exit 1
    fi
fi