#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据抽取工具使用示例
"""

from data_sampler import DataSampler

# 文件路径
input_file = "visfineval修正.xlsx"
output_file = "sampled_data.xlsx"

# 创建抽取器
sampler = DataSampler(input_file)

# 示例1: 查看数据信息
print("=" * 50)
print("示例1: 查看数据信息")
print("=" * 50)
sampler.show_column_info()

# 如果知道列名，可以查看特定列的信息
# sampler.show_column_info('列名')

# 示例2: 均匀抽取100条数据
print("\n" + "=" * 50)
print("示例2: 均匀抽取100条数据")
print("=" * 50)
result = sampler.uniform_sample(n=100, random_state=42)
print(f"抽取了 {len(result)} 条数据")
# result.to_excel("uniform_sample.xlsx", index=False)

# 示例3: 随机抽取10%的数据
print("\n" + "=" * 50)
print("示例3: 随机抽取10%的数据")
print("=" * 50)
result = sampler.random_sample(ratio=0.1, random_state=42)
print(f"抽取了 {len(result)} 条数据")
# result.to_excel("random_sample.xlsx", index=False)

# 示例4: 随机抽取500条数据
print("\n" + "=" * 50)
print("示例4: 随机抽取500条数据")
print("=" * 50)
result = sampler.random_sample(n=500, random_state=42)
print(f"抽取了 {len(result)} 条数据")
# result.to_excel("random_sample_500.xlsx", index=False)

# 示例5: 分层抽取（按比例，需要指定列名）
print("\n" + "=" * 50)
print("示例5: 分层抽取（按比例）")
print("=" * 50)
# 假设有一个名为'category'的列
# result = sampler.stratified_sample(
#     column='category',
#     n=1000,
#     strategy='proportional',
#     random_state=42
# )
# print(f"抽取了 {len(result)} 条数据")
# result.to_excel("stratified_proportional.xlsx", index=False)

# 示例6: 分层抽取（等量，每层抽取相同数量）
print("\n" + "=" * 50)
print("示例6: 分层抽取（等量）")
print("=" * 50)
# result = sampler.stratified_sample(
#     column='category',
#     n=1000,
#     strategy='equal',
#     random_state=42
# )
# print(f"抽取了 {len(result)} 条数据")
# result.to_excel("stratified_equal.xlsx", index=False)

# 示例7: 自定义分层抽取
print("\n" + "=" * 50)
print("示例7: 自定义分层抽取")
print("=" * 50)
# 假设有一个名为'category'的列，值为'A', 'B', 'C'
# custom_dict = {
#     'A': 100,      # A类抽取100条
#     'B': 0.2,      # B类抽取20%
#     'C': 50        # C类抽取50条
# }
# result = sampler.custom_stratified_sample(
#     column='category',
#     custom_dict=custom_dict,
#     random_state=42
# )
# print(f"抽取了 {len(result)} 条数据")
# result.to_excel("custom_stratified.xlsx", index=False)

print("\n" + "=" * 50)
print("提示: 取消注释上面的代码来实际执行抽取")
print("=" * 50)

