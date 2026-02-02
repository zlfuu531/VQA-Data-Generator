#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""专门测试多轮对话是否完整保留"""

from data_sampler import DataSampler
import pandas as pd

# 加载数据
sampler = DataSampler('所有数据.xlsx')

# 找到所有多轮对话的question_id
question_counts = sampler.df['question_id'].value_counts()
multi_round_qids = question_counts[question_counts > 1].index.tolist()
print(f"找到 {len(multi_round_qids)} 个多轮对话question_id")
print(f"最多轮次: {question_counts.max()} 轮")
print(f"\n前10个多轮对话question_id及其轮次数:")
for qid in multi_round_qids[:10]:
    count = question_counts[qid]
    print(f"  question_id={qid}: {count} 轮")

# 测试random_sample
print("\n" + "=" * 60)
print("测试 random_sample (n=200)")
print("=" * 60)
result = sampler.random_sample(n=200, random_state=42)
sampled_qids = result['question_id'].unique()
sampled_multi_round_qids = [qid for qid in sampled_qids if qid in multi_round_qids]

print(f"抽取的question_id总数: {len(sampled_qids)}")
print(f"其中多轮对话数量: {len(sampled_multi_round_qids)}")

# 检查每个多轮对话是否完整
all_complete = True
for qid in sampled_multi_round_qids[:10]:  # 检查前10个
    original_count = len(sampler.df[sampler.df['question_id'] == qid])
    sampled_count = len(result[result['question_id'] == qid])
    is_complete = original_count == sampled_count
    if not is_complete:
        all_complete = False
    print(f"question_id={qid}: 原始{original_count}轮, 抽取{sampled_count}轮, 完整: {is_complete}")

if all_complete and len(sampled_multi_round_qids) > 0:
    print(f"\n✓ 所有检查的多轮对话都完整保留！")
else:
    print(f"\n✗ 发现不完整的多轮对话！")

# 测试uniform_sample
print("\n" + "=" * 60)
print("测试 uniform_sample (n=100)")
print("=" * 60)
result2 = sampler.uniform_sample(n=100, random_state=42)
sampled_qids2 = result2['question_id'].unique()
sampled_multi_round_qids2 = [qid for qid in sampled_qids2 if qid in multi_round_qids]

print(f"抽取的question_id总数: {len(sampled_qids2)}")
print(f"其中多轮对话数量: {len(sampled_multi_round_qids2)}")

all_complete2 = True
for qid in sampled_multi_round_qids2[:10]:
    original_count = len(sampler.df[sampler.df['question_id'] == qid])
    sampled_count = len(result2[result2['question_id'] == qid])
    is_complete = original_count == sampled_count
    if not is_complete:
        all_complete2 = False
    print(f"question_id={qid}: 原始{original_count}轮, 抽取{sampled_count}轮, 完整: {is_complete}")

if all_complete2 and len(sampled_multi_round_qids2) > 0:
    print(f"\n✓ 所有检查的多轮对话都完整保留！")
else:
    print(f"\n✗ 发现不完整的多轮对话！")

# 测试stratified_sample（如果有多轮对话的列）
print("\n" + "=" * 60)
print("测试 stratified_sample (按difficulty分层, n=100)")
print("=" * 60)
if 'difficulty' in sampler.df.columns:
    result3 = sampler.stratified_sample('difficulty', n=100, strategy='proportional', random_state=42)
    sampled_qids3 = result3['question_id'].unique()
    sampled_multi_round_qids3 = [qid for qid in sampled_qids3 if qid in multi_round_qids]
    
    print(f"抽取的question_id总数: {len(sampled_qids3)}")
    print(f"其中多轮对话数量: {len(sampled_multi_round_qids3)}")
    
    all_complete3 = True
    for qid in sampled_multi_round_qids3[:10]:
        original_count = len(sampler.df[sampler.df['question_id'] == qid])
        sampled_count = len(result3[result3['question_id'] == qid])
        is_complete = original_count == sampled_count
        if not is_complete:
            all_complete3 = False
        print(f"question_id={qid}: 原始{original_count}轮, 抽取{sampled_count}轮, 完整: {is_complete}")
    
    if all_complete3 and len(sampled_multi_round_qids3) > 0:
        print(f"\n✓ 所有检查的多轮对话都完整保留！")
    else:
        print(f"\n✗ 发现不完整的多轮对话！")

print("\n" + "=" * 60)
print("测试完成！")
print("=" * 60)

