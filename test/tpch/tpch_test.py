import json
import math
import os
import time
import psycopg2
import random
import math
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import execute
import plot 
import shutil
import time, torch
import multiprocessing as mp
from functools import partial
from multiprocessing import Manager
import re
import execute
DB_CONFIG = {
    "dbname": "postgres",
    "user": "postgres",
    "host": "localhost",
    "port": "44444"
}

# workload dir
SQL_DIR = "./tpch_query"   
VIDEX_SQL_DIR = "./videx_query"     
# data dir after split
BATCH_DIR = "/home/yyk/Sqms-On-Postgresql/contrib/sqms/test2/tbl_batches"       
# create table file
CREATE_FILE = "tpch-create.sql"   
VIDEX_CREATE_FILE = "videx-create.sql"    
tpch_tbl_list = ["lineitem", "orders", "part", "partsupp", "customer", "nation", "region", "supplier"]

PKEYS_FILE = "tpch-pkeys.sql"
VIDEX_PKEYS_FILE = "videx-pkeys.sql"

FKEYS_FILE = "tpch-alter.sql"

CREATE_IDX_FILE = "tpch-index.sql"
DROP_IDX_FILE = "tpch-index-drop.sql"

OUTPUT_DIR = "output" 

def InitEnv(conn):
    init_data_size = 1
    cursor = conn.cursor()
    #re-create tables
    print("Creating tables...")
    for tbl_name in tpch_tbl_list:
        cursor.execute(f"DROP TABLE IF EXISTS {tbl_name} CASCADE")
        cursor.execute(f"DROP TABLE IF EXISTS v_{tbl_name} CASCADE")
    status = execute.execute_sql_file(cursor,CREATE_FILE,False)
    status = execute.execute_sql_file(cursor,VIDEX_CREATE_FILE,False)
    #clear index
    status = execute.execute_sql_file(cursor,DROP_IDX_FILE,False)
    status = execute.execute_sql_file(cursor,CREATE_IDX_FILE,False)
    #set primary key
    status = execute.execute_sql_file(cursor,PKEYS_FILE,False)
    status = execute.execute_sql_file(cursor,VIDEX_PKEYS_FILE,False)
    #set foreign key
    #status = execute.execute_sql_file(cursor,FKEYS_FILE,False)
    
    #import data
    for batch_index in range(init_data_size):
        print(f"[ batch {batch_index + 1} ] Begin importing data...")
        for tbl_name in tpch_tbl_list:
            tbl_path = f"{BATCH_DIR}/{tbl_name}_batch_{batch_index}.tbl"
            print(f"copy {tbl_name} from '{tbl_path}' with delimiter as '|' NULL '' ")
            cursor.execute(f"copy {tbl_name} from '{tbl_path}' with delimiter as '|' NULL '' ")
            print(f"[ batch {batch_index + 1}] Finish importing data...")

    for tbl_name in tpch_tbl_list:
        cursor.execute(f"ANALYZE {tbl_name}")
        cursor.execute(f"SELECT videx_analyze('{tbl_name}'::regclass, 'v_{tbl_name}'::regclass)")
    cursor.close()
    return 

def classify_sql_statements(raw_sql):
    
    statements = [stmt.strip() for stmt in raw_sql.split(';') if stmt.strip()]
    create_stmts, select_stmts, drop_stmts = [], [], []

    for stmt in statements:
        normalized = re.sub(r'--.*', '', stmt).strip().lower()
        first_word = re.match(r'^\s*(\w+)', normalized)
        if not first_word:
            continue
        keyword = first_word.group(1)
        if keyword == 'create':
            create_stmts.append(stmt)
        elif keyword == 'select':
            select_stmts.append(stmt)
        elif keyword == 'drop':
            drop_stmts.append(stmt)
        else:
            print(f"unregnoize sql type: {stmt[:30]}...")

    return create_stmts, select_stmts, drop_stmts


def init_conn():
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = True
    return conn

def process_one_sql_for_plan(dir,sql_file, repeat,output_name):
    conn = init_conn()
    cursor = conn.cursor()
    sql_path = os.path.join(dir, sql_file)
    sql_name = os.path.splitext(sql_file)[0]
    output_path = os.path.join(OUTPUT_DIR, f"{output_name}.txt")

    print(f"Start processing {sql_file}")
    success_count = 0

    with open(sql_path, 'r', encoding='utf-8') as f:
        raw_sql = f.read()
    
    create_stmts, select_stmts, drop_stmts = classify_sql_statements(raw_sql)

    with open(output_path, 'w', encoding='utf-8') as f_out:
        for i in range(repeat):
            try:
                for create_stmt in create_stmts:
                    try:
                        cursor.execute(create_stmt)
                    except Exception as e:
                        print(f"[{sql_file} #{i}] Create failed: {e}")
                        conn.rollback()
                for select_stmt in select_stmts:
                    try:
                        explain_sql = f"EXPLAIN (FORMAT JSON) {select_stmt}"
                        cursor.execute(explain_sql)
                        plan = cursor.fetchall()
                        formatted_json = json.dumps(plan[0][0], indent=2)
                        #f_out.write(json.dumps(plan) + "\n")
                        f_out.write(formatted_json + "\n")
                        success_count += 1
                    except Exception as e:
                        print(f"[{sql_file} #{i}] Error during EXPLAIN: {e}")
                        conn.rollback()
                for drop_stmt in drop_stmts:
                    try:
                        cursor.execute(drop_stmt)
                        conn.commit()
                    except Exception as e:
                        print(f"[{sql_file} #{i}] Drop failed: {e}")
                        conn.rollback()
            except Exception as e:
                print(f"[{sql_file} #{i}] Outer error: {e}")
                conn.rollback()

    cursor.close()
    conn.close()
    print(f"Finished {sql_file} with {success_count}/{repeat} successful plans.")

def compare_test():
    conn = init_conn()
    InitEnv(conn)

    sql_files = [f for f in os.listdir(SQL_DIR) if f.endswith(".sql")]
    for sql_file in sql_files:
        print(f"Processing {sql_file}...")
        process_one_sql_for_plan(SQL_DIR,sql_file, 1,sql_file)

    videx_sql_files = [f for f in os.listdir(VIDEX_SQL_DIR) if f.endswith(".sql")]
    for sql_file in videx_sql_files:
        print(f"Processing {sql_file}...")
        process_one_sql_for_plan(VIDEX_SQL_DIR,sql_file, 1,"videx_" + sql_file)
    print("All SQL files processed.")
    return 

if __name__ == "__main__":
    compare_test()