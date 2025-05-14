# Installation Guide

<p align="center">
  <a href="./installation.md">English</a> |
  <a href="./installation_zh.md">简体中文</a>
</p>


VIDEX supports the following installation methods:

1. Compile a complete MySQL Server (including VIDEX engine)
2. Compile VIDEX plugin and install it on an existing MySQL Server
3. Use Docker image installation method

## 1. Preparation

### 1.1 Download Code

> Using Percona-MySQL 8.0.34-26 as an example.

```bash
cd ~/code
VIDEX_HOME=$(pwd)/videx_server
MySQL8_HOME=$(pwd)/mysql_server

# Clone repositories
git clone git@github.com:bytedance/videx.git $VIDEX_HOME
git clone --depth=1 --recursive -b release-8.0.34-26 https://github.com/percona/percona-server.git $MySQL8_HOME

# Download Boost library to speed up installation
mkdir $MySQL8_HOME/boost && cd $MySQL8_HOME/boost
wget https://archives.boost.io/release/1.77.0/source/boost_1_77_0.tar.bz2
tar -xvjf boost_1_77_0.tar.bz2
```

### 1.2 Install Dependencies

VIDEX depends on the following components:
- MySQL build environment: gcc, cmake, bison, etc. (see `build/Dockerfile.build_env`)
- Python 3.9

> Tip: Refer to `build/Dockerfile.build_env` for setting up a complete build environment

## 2. Installation Method 1: Compile Complete MySQL Server

This step is an alternative to [3. Installation Method 2: Compile VIDEX Plugin](#3-installation-method-2-compile-videx-plugin). 
This method will compile a complete MySQL Server with the VIDEX engine included.

```bash
# Build
cd $VIDEX_HOME/build && bash build.sh
```

> Note: You can customize the following in `build/config.sh`:
> - VIDEX/MySQL repository locations
> - MySQL/VIDEX service ports
> - Other configuration options

## 3. Installation Method 2: Compile VIDEX Plugin

This method only compiles the VIDEX plugin, which can be installed on an existing MySQL Server.

This step is an alternative to [2. Installation Method 1: Compile Complete MySQL Server](#2-installation-method-1-compile-complete-mysql-server).
Users can compile just the videx plugin and install it on a running mysql-server.

> Important: The MySQL version in the build environment must exactly match the target MySQL Server version

### 3.1 Compile Plugin
```bash
cd $VIDEX_HOME/build && bash build_videx.sh
```
The plugin file `ha_videx.so` will be generated in `mysql_build_output/build/plugin_output_directory/`

### 3.2 Install Plugin

1. Check MySQL plugin directory:

```sql
SHOW VARIABLES LIKE "%plugin%"
+-----------------+---------------------------------------+
| Variable_name   | Value                                 |
+-----------------+---------------------------------------+
| plugin_dir      | /path/to/percona-mysql-8/lib/plugin/  |
+-----------------+---------------------------------------+
```

2. Copy plugin to plugin directory:
```bash
cp ha_videx.so /path/to/percona-mysql-8/lib/plugin/
```

3. Install plugin:
```sql
INSTALL PLUGIN VIDEX SONAME 'ha_videx.so';
```

4. Verify installation:
```sql
SHOW ENGINES;  -- VIDEX should appear in the engine list
```

## 4. Start Service

### 4.1 Complete Environment Startup

If you compiled a complete MySQL Server (Installation Method 1), you can use scripts to start everything with one command:

1. Initialize service:
```bash
cd $VIDEX_HOME/build && bash init_server.sh
```

2. Start service:
```bash
cd $VIDEX_HOME/build && bash start_server.sh
```

### 4.2 Start VIDEX Server Independently

1. Prepare Python environment:
```bash
cd $VIDEX_HOME
conda create -n videx_py39 python=3.9
conda activate videx_py39
python3.9 -m pip install -e . --use-pep517
```

2. Start service:
```bash
cd $VIDEX_HOME/src/sub_platforms/sql_opt/videx/scripts
python start_videx_server.py --port 5001
```

## 5. Installation Method 3: Using Docker Image

### 5.1 Preparation

First, complete step 1: download the VIDEX and MySQL code.  
Ensure that the VIDEX and MySQL code are in the same directory, named `videx_server` and `mysql_server` respectively. 
You may use symbolic links.

### 5.2 Build and Run Docker Image

1. Build the environment image:
```bash
cd videx_server
docker build -t videx_build:latest -f build/Dockerfile.build_env .
```

2. Build the VIDEX image:
```bash
docker build -t videx:latest -f build/Dockerfile.videx ..
```

> Note: This process requires significant memory resources (at least 8GB Docker memory is recommended).

3. Run the Docker image:
```bash
docker run -d --name videx-server \
  -p 13308:13308 \
  -p 5001:5001 \
  videx:latest
```