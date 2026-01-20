"""
Copyright (c) 2024 Bytedance Ltd. and/or its affiliates
SPDX-License-Identifier: MIT
"""

import argparse
import json
import logging
import os

from sub_platforms.sql_opt.env.rds_env import OpenPGEnv
from sub_platforms.sql_opt.videx import videx_logging
from sub_platforms.sql_opt.videx.videx_pg_metadata import (
    fetch_all_meta_with_one_file_for_pg,
    construct_videx_task_meta_from_local_files_for_pg,
)
from sub_platforms.sql_opt.videx.videx_service import (
    create_videx_env_multi_db_for_pg,
    post_add_videx_meta,
)
from sub_platforms.sql_opt.videx.videx_utils import VIDEX_IP_WHITE_LIST


def get_usage_message(args, videx_ip, videx_port, videx_db, videx_user, videx_pwd, videx_server_ip_port):
    base_msg = f"Build env finished. Your VIDEX server is {videx_server_ip_port}."

    if args.task_id:
        videx_options = json.dumps({"task_id": args.task_id})
        return (
            f"{base_msg}\n"
            f"To use VIDEX, please set the following variable before explaining your SQL:\n" + "-" * 20 + "\n"
            f"-- Connect VIDEX-PG: psql -h{videx_ip} -p{videx_port} -U{videx_user} -d{videx_db}\n"
            f"\\c {videx_db};\n"
            f"SET @VIDEX_SERVER='{videx_server_ip_port}';\n"
            f"SET @VIDEX_OPTIONS='{videx_options}';\n"
            f"-- EXPLAIN YOUR_SQL;\n"
        )

    return (
        f"{base_msg}\n"
        f"You are running in non-task mode.\n"
        f"To use VIDEX, please set the following variable before explaining your SQL:\n" + "-" * 20 + "\n"
        f"-- Connect VIDEX-PG: psql -h{videx_ip} -p{videx_port} -U{videx_user} -d{videx_db}\n"
        f"\\c {videx_db};\n"
        f"SET @VIDEX_SERVER='{videx_server_ip_port}';\n"
        f"-- EXPLAIN YOUR_SQL;\n"
    )

def parse_connection_info(info: str):
    target_ip, target_port, target_db, target_user, target_pwd = info.split(':')
    return target_ip, int(target_port), target_db, target_user, target_pwd


def main():
    """Collect PG metadata from `target`, then create a VIDEX-PG env and post metadata to VIDEX server."""

    parser = argparse.ArgumentParser(description='Collect data from target_ins and create videx environment (PG-only).')
    parser.add_argument('--target', type=str, required=True,
                        help='Connection info for raw instance, in the format of "ip:port:db:user:password"')
    parser.add_argument('--videx', type=str,
                        help='Connection info for videx instance, in the format of "ip:port:db:user:password". '
                             'If not provided, it will be generated based on raw instance info.')
    parser.add_argument('--videx_server', type=str, default="5001",
                        help='Connection info for videx server, in the format of "[ip:]port". '
                             'If not provided, access "{videx_ip}:5001".')
    parser.add_argument('--tables', type=str, default=None,
                        help='Comma-separated list of table names to fetch. If not provided, fetching all tables. '
                             'e.g. customer,nation')
    parser.add_argument('--meta_path', type=str, default=None,
                        help='meta filepath to save pulled metadata.')
    parser.add_argument('--fetch_method', type=str, default='fetch',
                        help='fetch, partial_fetch (PG-only: treated as fetch)')
    parser.add_argument('--task_id', type=str, default=None,
                        help='task id is to distinguish different videx tasks, if they have same database names.')

    videx_logging.initial_config()
    args = parser.parse_args()

    target_ip, target_port, target_db, target_user, target_pwd = parse_connection_info(args.target)

    if args.videx:
        videx_ip, videx_port, videx_db, videx_user, videx_pwd = parse_connection_info(args.videx)
    else:
        videx_ip, videx_port, videx_user, videx_pwd = target_ip, target_port, target_user, target_pwd
        videx_db = f'videx_{target_db}'

    if target_ip == videx_ip and target_port == videx_port:
        assert target_db != videx_db, (
            f"Since `target_ins` and `videx_ins` are the same instance, their `db` properties must not be the same."
        )

    if ':' in args.videx_server:
        videx_server_ip_port = args.videx_server
    else:
        videx_server_ip_port = f"{videx_ip}:{args.videx_server}"

    target_env = OpenPGEnv(ip=target_ip, port=target_port, usr=target_user, pwd=target_pwd, db_name=target_db,
                           read_timeout=300, write_timeout=300, connect_timeout=10)

    videx_env = OpenPGEnv(ip=videx_ip, port=videx_port, usr=videx_user, pwd=videx_pwd, db_name=videx_db,
                          read_timeout=300, write_timeout=300, connect_timeout=10)

    if args.tables:
        all_table_names = args.tables.split(',')
    else:
        all_table_names = None

    if args.meta_path:
        meta_path = args.meta_path
        if os.path.dirname(meta_path):
            os.makedirs(os.path.dirname(meta_path), exist_ok=True)
    else:
        meta_path = None
    logging.info(f"metadata file is {meta_path}")

    if args.fetch_method not in ['fetch', 'partial_fetch']:
        raise NotImplementedError(
            f"Fetching method `{args.fetch_method}` not implemented for PG-only build. Only support `fetch`."
        )

    # step 2: fetch/read metadata and statistics
    VIDEX_IP_WHITE_LIST.append(target_ip)
    files = fetch_all_meta_with_one_file_for_pg(
        meta_path=meta_path,
        env=target_env,
        target_db=target_db,
        all_table_names=all_table_names,
    )
    stats_file_dict, statistic_file_dict, ndv_single_file_dict, ndv_mulcol_file_dict = files

    meta_request = construct_videx_task_meta_from_local_files_for_pg(
        task_id=args.task_id,
        videx_db=videx_db,
        stats_file=stats_file_dict,
        statistic_file=statistic_file_dict,
        raise_error=True,
    )

    # step 3: create tables into VIDEX-PG, then post metadata/statistics to VIDEX-Server
    create_videx_env_multi_db_for_pg(videx_env, meta_dict=meta_request.meta_dict)

    response = post_add_videx_meta(meta_request, videx_server_ip_port=videx_server_ip_port, use_gzip=True)
    assert response.status_code == 200

    logging.info(get_usage_message(args, videx_ip, videx_port, videx_db, videx_user, videx_pwd, videx_server_ip_port))


if __name__ == "__main__":
    main()
