# -*- coding: utf-8 -*-
"""
Copyright (c) 2024 Bytedance Ltd. and/or its affiliates
SPDX-License-Identifier: MIT

@ author: kangrong.cn
@ date: 2025-03-06

CREATE TABLE `request_info` (
    `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键 ID',
  `query` text COMMENT '请求query信息',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  KEY `idx_created_at` (`created_at`)
) ENGINE=InnoDB
"""
import logging
import time
from datetime import datetime, timedelta
import pandas as pd
import string
import random
from sub_platforms.sql_opt.env.rds_env import OpenMySQLEnv
from sub_platforms.sql_opt.videx import videx_logging


def generate_random_query(length=200):
    """生成仅包含小写字母a-z的随机字符串"""
    return ''.join(random.choice(string.ascii_lowercase) for _ in range(length))


def get_system_info(parse_env):
    query = """
    SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_ROWS, AVG_ROW_LENGTH, DATA_LENGTH, 
           MAX_DATA_LENGTH, INDEX_LENGTH, DATA_FREE
    FROM information_schema.TABLES 
    WHERE TABLE_NAME = 'request_info' and ENGINE = 'InnoDB'
    """

    res = parse_env.query_for_dataframe(query)
    res = res.iloc[0].to_dict()

    query = """
    select TABLE_NAME, N_ROWS,CLUSTERED_INDEX_SIZE, SUM_OF_OTHER_INDEX_SIZES 
        from `mysql`.`innodb_table_stats` where TABLE_NAME = 'request_info'
        """

    res2 = parse_env.query_for_dataframe(query)
    res2 = res2.iloc[0].to_dict()
    # 合并字典 res, res2
    res.update(res2)
    return res


def insert_batch_data(parse_env, current_time, batch_size):
    # 生成批量数据
    queries = [generate_random_query() for _ in range(batch_size)]

    # 构建插入数据的DataFrame
    df = pd.DataFrame({
        'created_at': current_time,
        'query': queries
    })

    # 构建插入SQL
    insert_sql = "INSERT INTO request_info (created_at, query) VALUES "
    values = []
    for _, row in df.iterrows():
        values.append(f"('{row['created_at']}', '{row['query']}')")

    insert_sql += ",".join(values)

    # 执行插入
    parse_env.execute(insert_sql)
    return len(df)


def delete_old_data(parse_env, current_time, days):
    delete_time = current_time - timedelta(days=days)
    delete_sql = f"DELETE FROM request_info WHERE created_at < '{delete_time}'"

    # 记录删除操作的开始时间
    start_time = time.time()
    result = parse_env.execute(delete_sql)
    delete_duration = time.time() - start_time

    return result, delete_duration


def main():
    videx_logging.initial_config()
    # 配置参数
    scale_factor = 10000
    start_time = datetime(2022, 1, 1)  # 从2024年1月1日开始
    end_time = start_time + timedelta(days=300)
    batch_size = int(scale_factor)

    # 数据库连接
    parse_env = None # blabla

    parse_env.execute("drop table if exists request_info")

    has_create_index = True
    logging.info(f"#@#@# has_create_index: {has_create_index}")
    if has_create_index:
        create_ddl = """
        CREATE TABLE `request_info` (
          `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键 ID',
          `query` text COMMENT '请求query信息',
          `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '创建时间',
          PRIMARY KEY (`id`),
          KEY `idx_created_at` (`created_at`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    else:
        create_ddl = """
        CREATE TABLE `request_info` (
          `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键 ID',
          `query` text COMMENT '请求query信息',
          `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '创建时间',
          PRIMARY KEY (`id`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    parse_env.execute(create_ddl)

    last_check_time = start_time
    total_inserted = 0
    current_time = start_time

    try:
        while current_time < end_time:
            # 每分钟插入数据
            inserted = insert_batch_data(parse_env, current_time, batch_size)
            total_inserted += inserted
            logging.info(f"Time: {current_time}, Inserted {inserted} records, total: {total_inserted}")

            # 每两天检查一次系统信息
            if (current_time - last_check_time).days >= 2:
                logging.info(f"\n=== System Info Before Deletion at {current_time} ===")
                system_info = get_system_info(parse_env)
                logging.info(system_info)

                # 删除旧数据
                deleted, delete_duration = delete_old_data(parse_env, current_time, 2)
                logging.info(f"\nDeleted {deleted} records in {delete_duration:.2f} seconds")

                logging.info(f"\n=== System Info After Deletion at {current_time} ===")
                system_info = get_system_info(parse_env)
                logging.info(system_info)

                last_check_time = current_time

            # 时间前进一分钟
            current_time += timedelta(days=1)

    except KeyboardInterrupt:
        logging.info("\nScript interrupted by user")
    finally:
        logging.info(f"\nFinal System Info at {current_time}:")
        system_info = get_system_info(parse_env)
        logging.info(system_info)


if __name__ == "__main__":
    main()
