"""
Copyright (c) 2024 Bytedance Ltd. and/or its affiliates
SPDX-License-Identifier: MIT

@ author: kangrong
@ date: 2025-03-13

Function description:
1. Obtain the event_time data from the stream_event table.
2. Analyze the distribution of event_time:
    - Calculate the correlation coefficient between the actual data and the theoretical uniform distribution.
    - Draw a cumulative distribution plot to compare the actual distribution with the uniform distribution.
    - Output the basic statistical information.
3. Visualize the results to help determine whether the data conforms to a uniform distribution.

"""

import matplotlib.pyplot as plt
import numpy as np

from sub_platforms.sql_opt.env.rds_env import OpenMySQLEnv


def fetch_data(env):
    # 获取event_time数据
    query = "SELECT event_time FROM stream_event where event_time > '2000-01-01' and event_time < '2030-01-01'"
    df = env.query_for_dataframe(query)
    return df['event_time']


def analyze_distribution(data):
    # 将时间戳转换为相对时间（以小时为单位）
    min_time = data.min()
    time_deltas = [(t - min_time).total_seconds() / 3600 for t in data]  # 转换为小时
    sorted_data = np.sort(time_deltas)

    # 计算累积分布
    cumulative_prob = np.arange(1, len(sorted_data) + 1) / len(sorted_data)

    # 计算理论均匀分布
    uniform_theoretical = np.linspace(min(sorted_data), max(sorted_data), len(sorted_data))
    uniform_prob = np.arange(1, len(uniform_theoretical) + 1) / len(uniform_theoretical)

    # 计算相关系数
    correlation = np.corrcoef(sorted_data, cumulative_prob)[0,1]

    # 绘制散点图
    plt.figure(figsize=(10, 6))
    plt.scatter(sorted_data, cumulative_prob, alpha=0.5, label='Actual Distribution')
    plt.plot(uniform_theoretical, uniform_prob, 'r--', label='Uniform Distribution')

    plt.xlabel('Hours since start')
    plt.ylabel('Cumulative Probability')
    plt.title(f'Cumulative Distribution of Event Times\nCorrelation with Uniform: {correlation:.4f}')
    plt.legend()
    plt.grid(True)

    # 添加起始时间信息
    plt.figtext(0.02, 0.02, f'Start time: {min_time}', size='small')

    plt.show()

    return correlation


def main():
    # 建立数据库连接
    env = None # blabla

    # 获取数据
    data = fetch_data(env)

    if not data.empty:
        # 分析分布
        correlation = analyze_distribution(data)
        print(f"Correlation coefficient with uniform distribution: {correlation:.4f}")

        # 计算基本统计量
        print("\nBasic statistics:")
        print(f"Count: {len(data)}")
        print(f"Mean: {data.mean():.2f}")
        print(f"Std: {data.std()}")
        print(f"Min: {data.min():.2f}")
        print(f"Max: {data.max():.2f}")


if __name__ == "__main__":
    main()
