import math
import os
import time
import psycopg2
import random
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from multiprocessing import Manager
import re
import re

def classify_sql_statements(raw_sql):
    raw_sql = '\n'.join(raw_sql.strip().splitlines()[1:])
    statements = [stmt.strip() for stmt in raw_sql.split(';') if stmt.strip()]
    create_stmts, select_stmts, drop_stmts = [], [], []

    ignore_keywords = {'begin', 'commit', 'end', 'start', 'rollback', 'savepoint', 'release'}

    for stmt in statements:
        normalized = re.sub(r'--.*', '', stmt).strip().lower()
        first_word_match = re.match(r'^\s*(\w+)', normalized)
        if not first_word_match:
            continue
        keyword = first_word_match.group(1)
        if keyword in ignore_keywords:
            continue
        if keyword == 'create':
            create_stmts.append(stmt)
        elif keyword == 'select':
            select_stmts.append(stmt)
        elif keyword == 'drop':
            drop_stmts.append(stmt)
    print(f"create_stmts:{create_stmts}")
    print(f"select_stmts:{select_stmts}")
    print(f"drop_stmts:{drop_stmts}")
    return create_stmts, select_stmts, drop_stmts

def execute_explain_sql_file(conn, file_path, select=True):
    plan_dict = None
    cursor = conn.cursor()

    with open(file_path, 'r', encoding='utf-8') as f:
        raw_sql = f.read()
    
    create_stmts, select_stmts, drop_stmts = classify_sql_statements(raw_sql)

    try:
        # CREATE
        for create_stmt in create_stmts:
            try:
                cursor.execute(create_stmt)
            except Exception as e:
                print(f"[{file_path}] Create failed: {e}")
                conn.rollback()

        # EXPLAIN SELECT
        if select:
            for select_stmt in select_stmts:
                try:
                    explain_sql = f"EXPLAIN (FORMAT JSON, ANALYZE) {select_stmt}"
                    cursor.execute(explain_sql)
                    plan = cursor.fetchall()
                    if plan and isinstance(plan[0][0], list):
                        plan_dict = plan[0][0][0]['Plan']
                    else:
                        print(f"[{file_path}] Invalid plan format")
                except Exception as e:
                    print(f"[{file_path}] Error during EXPLAIN: {e}")
                    conn.rollback()

        # DROP
        for drop_stmt in drop_stmts:
            try:
                cursor.execute(drop_stmt)
                conn.commit()
            except Exception as e:
                print(f"[{file_path}] Drop failed: {e}")
                conn.rollback()

    except Exception as e:
        print(f"[{file_path}] Outer error: {e}")
        conn.rollback()

    cursor.close()
    return plan_dict



# execute single sql
def execute_sql_file(cursor, file_path,select = True):
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    sql = "".join(lines)
    if select:
        # Skip the first three lines (comments)
        sql = "".join(lines[5:])
        if not sql.strip():
            print(f"Skipping {file_path}: No valid SQL found.")
            return "SKIPPED"

    try:
        cursor.execute(sql)
        if cursor.description: 
            results = cursor.fetchall()
            print(f"Results from {file_path}:")
            for row in results:
                print(row)
        else:
            print(f"Executed {file_path} (no results to fetch)")
        return "OK"

    except psycopg2.OperationalError as e:
        if "canceling statement due to user request" in str(e):
            print(f"Query cancelled by user in {file_path}")
            return "CANCELLED"
        else:
            print(f"OperationalError in {file_path}: {e}")
            return "ERROR"

    except psycopg2.ProgrammingError as e:
        print(f"ProgrammingError in {file_path}: {e}")
        return "ERROR"
    
