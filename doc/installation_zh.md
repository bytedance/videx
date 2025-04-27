# Installation Guide

<p align="center">
  <a href="./installation.md">English</a> |
  <a href="./installation_zh.md">简体中文</a>
</p>


VIDEX 支持以下安装方式：

1. 编译完整的 MySQL Server (包含 VIDEX 引擎)
2. 编译 VIDEX 插件并安装到现有 MySQL Server

## 1. 准备工作

### 1.1 下载代码

> 以 Percona-MySQL 8.0.34-26 为例。

```bash
cd ~/code
VIDEX_HOME=$(pwd)/videx_server
MySQL8_HOME=$(pwd)/mysql_server

# 克隆代码仓库
git clone git@github.com:bytedance/videx.git $VIDEX_HOME
git clone --depth=1 --recursive -b release-8.0.34-26 https://github.com/percona/percona-server.git $MySQL8_HOME

# 下载 Boost 库，加速安装
mkdir $MySQL8_HOME/boost && cd $MySQL8_HOME/boost
wget https://archives.boost.io/release/1.77.0/source/boost_1_77_0.tar.bz2
tar -xvjf boost_1_77_0.tar.bz2
```

### 1.2 安装依赖

VIDEX 依赖以下组件：
- MySQL 编译环境：gcc, cmake, bison 等（详见 `build/Dockerfile.build_env`）
- Python 3.9

> 提示：可参考 `build/Dockerfile.build_env` 准备完整的编译环境

## 2. 安装方式一：编译完整 MySQL Server

这一步是 [3. 安装方式二：编译 VIDEX 插件](#3-安装方式二编译-videx-插件) 的替代项。这种方式会编译一个包含 VIDEX 引擎的完整 MySQL Server。

```bash
# 编译
cd $VIDEX_HOME/build && bash build.sh
```

> 注：可通过修改 `build/config.sh` 自定义：
> - VIDEX/MySQL 代码仓库位置
> - MySQL/VIDEX 服务端口
> - 其他配置项

## 3. 安装方式二：编译 VIDEX 插件

这种方式仅编译 VIDEX 插件，可安装到现有的 MySQL Server。

这一步是 [2. 安装方式一：编译完整 MySQL Server](#2-安装方式一编译完整-mysql-server) 的替代项。
用户可以仅编译一个 videx 插件，然后安装到正在运行的 mysql-server 上。


> 重要：编译环境的 MySQL 版本必须与目标 MySQL Server 完全一致

### 3.1 编译插件
```bash
cd $VIDEX_HOME/build && bash build_videx.sh
```
插件文件 `ha_videx.so` 将生成在 `mysql_build_output/build/plugin_output_directory/`

### 3.2 安装插件

1. 查看 MySQL 插件目录：

```sql
SHOW VARIABLES LIKE "%plugin%"
+-----------------+---------------------------------------+
| Variable_name   | Value                                 |
+-----------------+---------------------------------------+
| plugin_dir      | /path/to/percona-mysql-8/lib/plugin/  |
+-----------------+---------------------------------------+
```

2. 拷贝插件到插件目录：
```bash
cp ha_videx.so /path/to/percona-mysql-8/lib/plugin/
```

3. 安装插件：
```sql
INSTALL PLUGIN VIDEX SONAME 'ha_videx.so';
```

4. 验证安装：
```sql
SHOW ENGINES;  -- VIDEX 应出现在引擎列表中
```

## 4. 启动服务

### 4.1 完整环境启动

如果您编译了完整的 MySQL Server（安装方式一），可以使用脚本一键启动：

1. 初始化服务：
```bash
cd $VIDEX_HOME/build && bash init_server.sh
```

2. 启动服务：
```bash
cd $VIDEX_HOME/build && bash start_server.sh
```

### 4.2 独立启动 VIDEX Server

1. 准备 Python 环境：
```bash
cd $VIDEX_HOME
conda create -n videx_py39 python=3.9
conda activate videx_py39
python3.9 -m pip install -e . --use-pep517
```

2. 启动服务：
```bash
cd $VIDEX_HOME/src/sub_platforms/sql_opt/videx/scripts
python start_videx_server.py --port 5001
```

## 5 安装方式三：编译 Docker 镜像

首先完成步骤 1：下载 VIDEX 和 MySQL 的代码。
请确保 VIDEX 和 MySQL 的代码位于同一目录下。并且目录名分别为 `videx_server` 和 `mysql_server`。你可以使用软链接。

然后执行以下命令：
```sql
cd videx_server
docker build -t videx:latest -f build/Dockerfile.videx ..
```