#!/usr/bin/env bash
set -e
set -x

/etc/init.d/ssh restart

git config --global --add safe.directory /root/mariadb-server

mkdir -p /root/mariadb-server/mysql_build_output/{ccache,build,data,logs,etc}

export CCACHE_DIR=/root/mariadb-server/mysql_build_output/ccache

if [ -d /root/mariadb-server/storage/videx ]; then
    echo "Videx directory already exists. Skipping copy."
else
    echo "Copying videx to mariadb-server..."
    cp -r /root/videx_server/src/mysql/videx /root/mariadb-server/storage/videx
fi

if [ -f /root/mariadb-server/mysql_build_output/etc/my.cnf ]; then
    echo "my.cnf already exists. Skipping copy."
else
    if [ -f /root/videx_server/build/my.cnf ]; then
        echo "Copying my.cnf to mariadb-server..."
        cp /root/videx_server/build/my.cnf /root/mariadb-server/mysql_build_output/etc/my.cnf
    else
        echo "Source my.cnf not found!"
        exit 1
    fi
fi