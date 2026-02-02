#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自定义抽取脚本：根据capability列进行分层抽取
- 少于200道的题目全部保留
- 图片文字双模态对齐四选单选题完全不抽
- 剩下的尽量均衡
"""

import pandas as pd
import numpy as np
from pathlib import Path

def custom_sample_by_capability(input_file, output_file, target_total=3000, random_state=42):
    """
    根据capability列进行自定义抽取
    
    Args:
        input_file: 输入Excel文件路径
        output_file: 输出Excel文件路径
        target_total: 目标总题目数
        random_state: 随机种子
    """
    # 读取数据
    df = pd.read_excel(input_file)
    print(f"原始数据: {len(df)} 题")
    
    # 设置随机种子
    if random_state is not None:
        np.random.seed(random_state)
    
    # 统计capability列
    capability_counts = df['capability'].value_counts()
    print("\n各capability的题目数:")
    for cap, count in capability_counts.items():
        print(f"  {cap}: {count} 题")
    
    # 分类处理
    exclude_capability = "图片文字双模态对齐四选单选题"
    sampled_dfs = []
    
    # 1. 排除不抽取的类别
    exclude_df = df[df['capability'] == exclude_capability]
    print(f"\n排除: {exclude_capability} - {len(exclude_df)} 题")
    
    # 2. 少于等于200道的全部保留（不包括排除的类别）
    small_capabilities = []
    for cap, count in capability_counts.items():
        if cap != exclude_capability and count <= 200:
            small_capabilities.append(cap)
            small_df = df[df['capability'] == cap]
            sampled_dfs.append(small_df)
            print(f"全部保留（<=200）: {cap} - {count} 题")
    
    small_total = sum(len(df[df['capability'] == cap]) for cap in small_capabilities)
    print(f"\n小类别总计: {small_total} 题")
    
    # 3. 剩下的类别需要均衡抽取
    remaining_needed = target_total - small_total
    print(f"剩余需要抽取: {remaining_needed} 题")
    
    # 获取需要抽取的类别（>200且不是排除的类别）
    large_capabilities = []
    for cap, count in capability_counts.items():
        if cap != exclude_capability and count > 200:
            large_capabilities.append(cap)
    
    print(f"\n需要均衡抽取的类别数: {len(large_capabilities)}")
    
    if remaining_needed <= 0:
        print("警告: 小类别总数已超过目标总数！")
        result = pd.concat(sampled_dfs, ignore_index=True)
    else:
        # 计算每个类别应该抽取的数量（尽量均衡）
        n_per_category = remaining_needed // len(large_capabilities)
        remainder = remaining_needed % len(large_capabilities)
        
        print(f"\n每个类别基础抽取数: {n_per_category} 题")
        if remainder > 0:
            print(f"前 {remainder} 个类别额外抽取1题")
        
        # 对每个大类别进行抽取
        for i, cap in enumerate(large_capabilities):
            cap_df = df[df['capability'] == cap]
            cap_count = len(cap_df)
            
            # 计算该类别应该抽取的数量
            if i < remainder:
                n_to_sample = n_per_category + 1
            else:
                n_to_sample = n_per_category
            
            # 确保不超过该类别总数
            n_to_sample = min(n_to_sample, cap_count)
            
            # 随机抽取
            if n_to_sample >= cap_count:
                sampled_dfs.append(cap_df)
                print(f"全部抽取: {cap} - {cap_count} 题")
            else:
                indices = np.random.choice(cap_count, size=n_to_sample, replace=False)
                sampled_df = cap_df.iloc[indices]
                sampled_dfs.append(sampled_df)
                print(f"抽取: {cap} - {n_to_sample}/{cap_count} 题")
        
        # 合并所有抽取的数据
        result = pd.concat(sampled_dfs, ignore_index=True)
        
        # 打乱顺序
        result = result.sample(frac=1, random_state=random_state).reset_index(drop=True)
    
    # 保存结果
    result.to_excel(output_file, index=False)
    
    print("\n" + "=" * 60)
    print("抽取完成！")
    print("=" * 60)
    print(f"原始数据: {len(df)} 题")
    print(f"抽取数据: {len(result)} 题")
    print(f"目标数量: {target_total} 题")
    print(f"差异: {len(result) - target_total} 题")
    
    # 显示抽取后的分布
    print("\n抽取后的capability分布:")
    result_counts = result['capability'].value_counts()
    for cap, count in result_counts.items():
        percentage = count / len(result) * 100
        print(f"  {cap}: {count} 题 ({percentage:.2f}%)")
    
    print(f"\n结果已保存到: {output_file}")
    
    return result

if __name__ == '__main__':
    import sys
    
    input_file = "visfineval修正.xlsx"
    if len(sys.argv) > 1:
        output_file = sys.argv[1]
    else:
        output_file = "sampled_3000.xlsx"
    
    if len(sys.argv) > 2:
        target_total = int(sys.argv[2])
    else:
        target_total = 3000
    
    if len(sys.argv) > 3:
        random_state = int(sys.argv[3])
    else:
        random_state = 42
    
    custom_sample_by_capability(input_file, output_file, target_total, random_state)

