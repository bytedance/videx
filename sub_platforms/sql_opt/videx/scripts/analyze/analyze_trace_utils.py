# -*- coding: utf-8 -*-
"""
Copyright (c) 2024 Bytedance Ltd. and/or its affiliates
SPDX-License-Identifier: MIT
"""
import json


def process_unknown_dict(unknown_dict):
    """process dict starting with unknown """
    processed = {}
    if 'request' in unknown_dict:
        try:
            request_json = json.loads(unknown_dict['request'])
            if 'properties' in request_json and 'function' in request_json['properties']:
                function_full = request_json['properties']['function']
                # 按 :: 分割并取最后一部分
                function_name = function_full.split('::')[-1].strip('()')
                processed['function'] = function_name
        except json.JSONDecodeError:
            processed['function'] = None

    if 'detail' in unknown_dict:
        try:
            # processed['detail'] = json.loads(unknown_dict['detail'])
            detail = json.loads(unknown_dict['detail'])
            new_detail = {'data': detail.get('data', {}).get('value', None), 'message': detail.get('message')}
            processed['detail'] = new_detail
        except json.JSONDecodeError:
            processed['detail'] = unknown_dict['detail']

    return processed


def process_videx_info_recursively(d):
    if not isinstance(d, dict):
        return d

    result = {}
    for key, value in d.items():
        if key.startswith('unknown_key_'):
            number = key.split('_')[-1]
            new_key = f'videx_{number}'
            result[new_key] = process_unknown_dict(value)
        else:
            if isinstance(value, dict):
                result[key] = process_videx_info_recursively(value)
            elif isinstance(value, list):
                result[key] = [process_videx_info_recursively(item) if isinstance(item, dict) else item for item in
                               value]
            else:
                result[key] = value

    return result


def find_key_paths(data, current_path=None, result=None):
    if current_path is None:
        current_path = []
    if result is None:
        result = []

    if isinstance(data, dict):
        # 如果遇到 attached_conditions_computation，保存整个字典
        if 'attached_conditions_computation' in data:
            result.append({
                'path': current_path + ['attached_conditions_computation'],
                'data': data  # 保存整个包含 attached_conditions_computation 的字典
            })
            return result  # 提前返回，不再继续递归处理这个分支

        # 检查是否包含其他关键的分析信息
        if 'range_analysis' in data and 'table_scan' in data['range_analysis']:
            result.append({
                'path': current_path + ['range_analysis', 'table_scan'],
                'data': data['range_analysis']['table_scan']
            })

        if 'range_analysis' in data and 'analyzing_range_alternatives' in data['range_analysis']:
            if 'range_scan_alternatives' in data['range_analysis']['analyzing_range_alternatives']:
                result.append({
                    'path': current_path + ['range_analysis', 'analyzing_range_alternatives',
                                            'range_scan_alternatives'],
                    'data': data['range_analysis']['analyzing_range_alternatives']['range_scan_alternatives']
                })

        if 'considered_execution_plans' in data and 'best_access_path' in data['considered_execution_plans']:
            result.append({
                'path': current_path + ['considered_execution_plans', 'best_access_path'],
                'data': data['considered_execution_plans']['best_access_path']
            })

        for key, value in data.items():
            find_key_paths(value, current_path + [key], result)

    elif isinstance(data, list):
        for item in data:
            find_key_paths(item, current_path, result)

    return result


def extract_key_trace_info(trace):
    """
    Extract key trace info from trace dict.
    The key parts include range_analysis, best_access_path, considered_execution_plans,
    and complete attached_conditions_computation structure.
    All of these reveal the reasons for index selection.

    :param trace:
    :return:
    """
    paths_and_data = find_key_paths(trace)

    result = {}
    for path_info in paths_and_data:
        current = result

        for i, path_part in enumerate(path_info['path'][:-1]):
            if isinstance(current, list):
                if not current:
                    current.append({})
                current = current[-1]

            if path_part not in current:
                if path_part == 'steps':
                    current[path_part] = []
                else:
                    current[path_part] = {}
            current = current[path_part]

        if isinstance(current, list):
            current.append(path_info['data'])
        else:
            current[path_info['path'][-1]] = path_info['data']

    result = process_videx_info_recursively(result)
    return result
