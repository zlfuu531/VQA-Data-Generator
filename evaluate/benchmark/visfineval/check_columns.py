#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速查看Excel文件的列信息
"""

import pandas as pd
import sys

if len(sys.argv) > 1:
    file_path = sys.argv[1]
else:
    file_path = "visfineval修正.xlsx"

try:
    df = pd.read_excel(file_path)
    print(f"文件: {file_path}")
    print(f"总行数: {len(df)}")
    print(f"总列数: {len(df.columns)}")
    print("\n列名列表:")
    for i, col in enumerate(df.columns, 1):
        print(f"  {i}. {col}")
    
    print("\n各列的详细信息:")
    for col in df.columns:
        print(f"\n列: {col}")
        print(f"  类型: {df[col].dtype}")
        print(f"  非空值数量: {df[col].notna().sum()}")
        print(f"  唯一值数量: {df[col].nunique()}")
        if df[col].nunique() <= 30:
            print(f"  值分布:")
            value_counts = df[col].value_counts()
            for val, count in value_counts.items():
                print(f"    {val}: {count} ({count/len(df)*100:.2f}%)")
        else:
            print(f"  前10个最常见的值:")
            for val, count in df[col].value_counts().head(10).items():
                print(f"    {val}: {count} ({count/len(df)*100:.2f}%)")
        
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()

