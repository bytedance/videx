"""
Copyright (c) 2024 Bytedance Ltd. and/or its affiliates
SPDX-License-Identifier: MIT

only for open-source, not for SQLBrain
"""
import logging
import logging.config
import logging.handlers
import os
import threading

import six
import yaml

videx_log_context = threading.local()
videx_log_context.__setattr__('videx_trace_id', '-')
videx_log_context.__setattr__('x_tt_log_id', '-')
videx_log_context.__setattr__('x_tt_trace_id', '-')


def get_trace_id():
    if hasattr(videx_log_context, 'videx_trace_id'):
        return videx_log_context.videx_trace_id
    else:
        return '-'


class VidexTraceIdFilter(logging.Filter):
    def filter(self, record):
        trace_id = get_trace_id()
        record._videx_trace_id = six.ensure_text(trace_id)
        for key in videx_log_context.__dict__.keys():
            if key == 'videx_trace_id':
                continue
            else:
                setattr(record, key, getattr(videx_log_context, key))
        return True


def set_thread_trace_id(trace_id: str):
    """
    设置日志TraceId，线程内有效
    Args:
        trace_id: trace_id
    Returns:
        None
    """
    videx_log_context.videx_trace_id = trace_id


def set_thread_local_property(property_name: str, property_value: str):
    """
    设置日志 roperty，线程内有效
    Args:
    Returns:
        None
    """
    setattr(videx_log_context, property_name, property_value)


def get_thread_local_property(property_name: str):
    """
    设置日志roperty，线程内有效
    Args:
    Returns:
        None
    """
    return getattr(videx_log_context, property_name)


def _read_config_from_file(file_path, log_file_prefix: str = None):
    print(os.getcwd())
    if not os.path.exists(file_path):
        raise Exception(f'not find log config file {file_path}')

    with open(file_path, 'rt') as f:
        config = yaml.safe_load(f.read())
        videx_trace_id_filters = {
            "videx_trace_filter": {
                "()": VidexTraceIdFilter,
            }
        }
        if 'filters' in config:
            config.get('filters').update(videx_trace_id_filters)
        else:
            config['filters'] = videx_trace_id_filters

        log_path = config.pop('log_path', './')
        try:
            if not os.path.exists(log_path):
                os.makedirs(log_path)
        except Exception as e1:
            print(f'can not create {log_path} {e1}')

        log_file_prefix_in_config = config.pop('log_file_prefix', 'videx_app')
        if log_file_prefix is not None:
            log_file_prefix_in_config = log_file_prefix

        for k, v in config.get('handlers', {}).items():
            if 'filters' in v:
                v.get('filters').append('videx_trace_filter')
            else:
                v['filters'] = ['videx_trace_filter']

            if 'filename' in v:
                v['filename'] = os.path.join(log_path,
                                             v['filename'].replace('${log_file_prefix}', log_file_prefix_in_config))

        return config


def default_videx_logging_config(log_file_prefix: str, log_path: str):
    return {
        'version': 1,
        'formatters': {
            'default': {
                'format': '%(asctime)s [%(process)d:%(thread)d] %(levelname)-8s %(name)-15s [%(filename)s:%(lineno)d] %(_videx_trace_id)s %(message)s',
                'datefmt': '%Y-%m-%d %H:%M:%S'
            }
        },
        'filters': {
            'videx_trace_filter': {
                '()': VidexTraceIdFilter
            },
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'formatter': 'default',
                'level': 'INFO',
                'stream': 'ext://sys.stdout',
                'filters': ['videx_trace_filter']
            },
            'info_log_file': {
                'class': 'logging.handlers.RotatingFileHandler',
                'formatter': 'default',
                'filename': f'{log_path}/{log_file_prefix}_info.log',
                'maxBytes': 100000000,
                'backupCount': 5,
                'filters': ['videx_trace_filter']
            },
            'error_log_file': {
                'class': 'logging.handlers.RotatingFileHandler',
                'formatter': 'default',
                'filename': f'{log_path}/{log_file_prefix}_error.log',
                'maxBytes': 100000000,
                'backupCount': 5,
                'filters': ['videx_trace_filter']
            },
        },
        'root': {
            'level': 'NOTSET',
            'handlers': ['console', 'info_log_file'],
            'propagate': False
        },
        'loggers': {
            'error_logger': {
                'level': 'ERROR',
                'handlers': ['error_log_file'],
                'propagate': True
            }
        }
    }


def initial_config(config_file: str = None, log_file_prefix: str = 'videx_app', log_path: str = './log'):
    """
    根据配置文件初始化日志配置
    Args:
        config_file: 配置文件地址，默认读取根目录log_config.yaml
        log_file_prefix: 日志文件前缀，默认videx_app
        log_path: 日志路径，默认 ./logs

    Returns:
        None
    """
    if config_file is None:
        config = default_videx_logging_config(log_file_prefix=log_file_prefix, log_path=log_path)
    else:
        config = _read_config_from_file(config_file, log_file_prefix=log_file_prefix)

    try:
        os.makedirs(log_path, exist_ok=True)
    except Exception as e:
        print(f'can not create {log_path=} {e}')

    print('logging config: ', config)
    logging.config.dictConfig(config)


if __name__ == '__main__':
    initial_config(log_file_prefix='try_videx', log_path='./videx_logs')
    import time
    set_thread_trace_id(f"<<task id: {123}>>")
    for i in range(5):
        logging.info(f"info {i}")
        logging.warning(f"info {i}")
        logging.error(f"info {i}")
        time.sleep(1)
