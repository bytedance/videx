克隆 MySQL 或 Percona 代码仓库（已验证 MySQL-server 8.0+ 和 Percona-server 8.0.34-26+）。

```bash
MySQL8_HOME=MySQL8_Server_Source
# mysql
git clone --depth=1 --recursive -b 8.0 https://github.com/mysql/mysql-server.git $MySQL8_HOME
# percona
git clone --depth=1 --recursive -b release-8.0.34-26 https://github.com/percona/percona-server.git $MySQL8_HOME

```

将 VIDEX-MySQL 相关代码拷贝到 `$MySQL8_HOME/storage`:

```bash
cp -r $VIDEX_HOME/src/mysql/videx $MySQL8_HOME/storage
```

生成 Makefile：

```bash
cmake .. \
    -B./build \
    -DWITH_DEBUG=0 \
    -DCMAKE_INSTALL_PREFIX=. \
    -DMYSQL_DATADIR=./data \
    -DSYSCONFDIR=./etc \
    -DWITH_BOOST=../boost \
    -DDOWNLOAD_BOOST=1 \
    -DWITH_ROCKSDB=OFF
```

编译：

```bash
cd $MySQL8_HOME/build/storage/videx/
make -j `nproc`
```

拷贝 `ha_videx.so` 到 `plugin_dir`:

```sql
SHOW VARIABLES LIKE "%plugin%";
+-----------------------------------------------+-----------------------------------------------+
| Variable_name                                 | Value                                         |
+-----------------------------------------------+-----------------------------------------------+
| default_authentication_plugin                 | caching_sha2_password                         |
| plugin_dir                                    | /root/mysql8/lib/plugin/ |
| replication_optimize_for_static_plugin_config | OFF                                           |
+-----------------------------------------------+-----------------------------------------------+

cp ha_videx.so /root/mysql8/lib/plugin/
```

安装插件：

```sql
INSTALL PLUGIN VIDEX SONAME 'ha_videx.so';
UNINSTALL PLUGIN VIDEX;
```

验证 VIDEX 已经成功安装，你会看到新增了一种引擎 VIDEX ：

```sql
SHOW ENGINES;
```