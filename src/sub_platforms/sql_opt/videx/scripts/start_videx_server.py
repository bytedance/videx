"""
Copyright (c) 2024 Bytedance Ltd. and/or its affiliates
SPDX-License-Identifier: MIT

@ author: kangrong
@ date: 2025-03-13
"""
import argparse
from typing import Type

from sub_platforms.sql_opt.videx.videx_metadata import PCT_CACHED_MODE_PREFER_META
from sub_platforms.sql_opt.videx.videx_service import startup_videx_server
from sub_platforms.sql_opt.videx.model.videx_strategy import VidexStrategy, VidexModelBase
from sub_platforms.sql_opt.videx.model.videx_model_innodb import VidexModelInnoDB
from sub_platforms.sql_opt.videx.model.videx_model_example import VidexModelExample

if __name__ == '__main__':
    """
    Examples:
        python start_videx_server.py --port 5001
    """
    parser = argparse.ArgumentParser(description='Start the Videx stats server.')
    parser.add_argument('--server_ip', type=str, default='0.0.0.0', help='The IP address to bind the server to.')
    parser.add_argument('--debug', action='store_true', help='Run the server in debug mode.')
    parser.add_argument('--port', type=int, default=5001, help='The port number to run the server on.')
    parser.add_argument('--strategy', type=str, default="innodb", help='innodb or other model')
    parser.add_argument('--cache_pct', type=float, default=PCT_CACHED_MODE_PREFER_META,
                        help='Table loaded cache percentage can significantly impact table scan costs. '
                             'If set to -1, it prefers to use values calculated from the system table. '
                             'If set to a float between 0 and 1, it forces the use of the specified value.')

    args = parser.parse_args()

    MainVidexModelClass: Type[VidexModelBase]
    """
    N.B. You can inherit VidexModeInnoDB, and then re-implement ndv and cardinality method.
    """
    if args.strategy == VidexStrategy.example.value:
        MainVidexModelClass = VidexModelExample
    elif args.strategy == VidexStrategy.innodb.value:
        MainVidexModelClass = VidexModelInnoDB
    else:
        raise NotImplementedError(f"Unsupported strategy: {args.strategy}")

    startup_videx_server(start_ip=args.server_ip, debug=args.debug, port=args.port,
                         VidexModelClass=MainVidexModelClass,
                         cache_pct=args.cache_pct,
                         )
