#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试修复后的数据抽样器"""

from data_sampler import DataSampler

# 加载数据
sampler = DataSampler('所有数据.xlsx')

print("=" * 60)
print("测试1: random_sample（抽取10个question_id）")
print("=" * 60)
result = sampler.random_sample(n=10, random_state=42)
print(f'抽取了 {len(result)} 行')
print(f'包含的question_id数量: {result["question_id"].nunique()}')

print('\n检查多轮对话是否完整:')
for qid in result['question_id'].unique()[:5]:
    qid_rows = result[result['question_id'] == qid]
    original_rows = sampler.df[sampler.df['question_id'] == qid]
    is_complete = len(qid_rows) == len(original_rows)
    print(f'question_id={qid}: 抽取了{len(qid_rows)}行, 原始有{len(original_rows)}行, 完整: {is_complete}')

# 测试多轮对话的question_id
multi_round_qid = sampler.df['question_id'].value_counts()
multi_round_qid = multi_round_qid[multi_round_qid > 1].index[0]
print(f'\n测试多轮对话question_id={multi_round_qid}:')
original_multi = sampler.df[sampler.df['question_id'] == multi_round_qid]
print(f'原始数据: {len(original_multi)} 行')

# 再次抽样，确保能抽到这个多轮对话
result2 = sampler.random_sample(n=100, random_state=42)
if multi_round_qid in result2['question_id'].values:
    sampled_multi = result2[result2['question_id'] == multi_round_qid]
    print(f'抽取后: {len(sampled_multi)} 行')
    print(f'多轮对话完整: {len(sampled_multi) == len(original_multi)}')
else:
    print(f'此次抽样未包含该question_id，需要增加抽样数量')

print("\n" + "=" * 60)
print("测试2: uniform_sample")
print("=" * 60)
result3 = sampler.uniform_sample(n=50, random_state=42)
print(f'抽取了 {len(result3)} 行')
print(f'包含的question_id数量: {result3["question_id"].nunique()}')

print("\n" + "=" * 60)
print("测试完成！")
print("=" * 60)

