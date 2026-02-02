#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据抽取工具
支持多种抽取方式：均匀抽取、随机抽取、分层抽取
可以按比例或按数量抽取
"""

import pandas as pd
import numpy as np
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Union
import random


class DataSampler:
    """数据抽取器"""
    
    def __init__(self, file_path: str, sheet_name: Optional[Union[str, int]] = 0):
        """
        初始化数据抽取器
        
        Args:
            file_path: Excel文件路径
            sheet_name: 工作表名称或索引，默认为0（第一个工作表）
        """
        self.file_path = file_path
        self.df = pd.read_excel(file_path, sheet_name=sheet_name)
        print(f"成功加载数据，共 {len(self.df)} 行，{len(self.df.columns)} 列")
        print(f"列名: {list(self.df.columns)}")
        
        # 检查是否有question_id列，用于多轮对话数据的分组
        self.question_id_col = 'question_id' if 'question_id' in self.df.columns else None
        if self.question_id_col:
            unique_questions = self.df[self.question_id_col].nunique()
            total_rows = len(self.df)
            print(f"检测到question_id列，共有 {unique_questions} 个唯一question_id（共 {total_rows} 行数据）")
    
    def _get_question_id_groups(self) -> Dict:
        """
        按question_id分组，返回question_id到行索引的映射
        
        Returns:
            Dict: {question_id: [行索引列表]}
        """
        if self.question_id_col is None:
            # 如果没有question_id列，将每一行作为一个独立的组
            return {i: [i] for i in range(len(self.df))}
        
        groups = {}
        for qid in self.df[self.question_id_col].unique():
            indices = self.df[self.df[self.question_id_col] == qid].index.tolist()
            groups[qid] = indices
        return groups
    
    def _sample_by_question_ids(self, selected_question_ids: List) -> pd.DataFrame:
        """
        根据选中的question_id列表，提取所有相关行（保证多轮对话完整）
        
        Args:
            selected_question_ids: 选中的question_id列表
        
        Returns:
            包含所有选中question_id的所有行的DataFrame
        """
        if self.question_id_col is None:
            # 如果没有question_id列，直接按索引提取
            return self.df.iloc[selected_question_ids].copy()
        
        mask = self.df[self.question_id_col].isin(selected_question_ids)
        return self.df[mask].copy()
    
    def uniform_sample(self, n: int, random_state: Optional[int] = None) -> pd.DataFrame:
        """
        均匀抽取：等间隔抽取数据（在question_id级别，保证多轮对话完整）
        
        Args:
            n: 抽取的question_id数量（注意：实际抽取的行数可能大于n，因为多轮对话）
            random_state: 随机种子（用于起始位置）
        
        Returns:
            抽取的数据
        """
        groups = self._get_question_id_groups()
        question_ids = sorted(groups.keys())
        total_questions = len(question_ids)
        
        if n >= total_questions:
            return self.df.copy()
        
        if random_state is not None:
            np.random.seed(random_state)
            start_idx = np.random.randint(0, max(1, total_questions // n))
        else:
            start_idx = 0
        
        step = max(1, total_questions // n)
        selected_indices = [start_idx + i * step for i in range(n) 
                           if start_idx + i * step < total_questions]
        selected_question_ids = [question_ids[i] for i in selected_indices]
        
        return self._sample_by_question_ids(selected_question_ids)
    
    def random_sample(self, n: Optional[int] = None, ratio: Optional[float] = None, 
                     random_state: Optional[int] = None) -> pd.DataFrame:
        """
        随机抽取（在question_id级别，保证多轮对话完整）
        
        Args:
            n: 抽取的question_id数量（与ratio二选一，注意：实际抽取的行数可能大于n）
            ratio: 抽取比例（0-1之间，与n二选一），基于question_id数量
            random_state: 随机种子
        
        Returns:
            抽取的数据
        """
        if n is None and ratio is None:
            raise ValueError("必须指定 n（数量）或 ratio（比例）")
        
        groups = self._get_question_id_groups()
        question_ids = list(groups.keys())
        total_questions = len(question_ids)
        
        if n is None:
            n = int(total_questions * ratio)
        
        if n >= total_questions:
            return self.df.copy()
        
        if random_state is not None:
            np.random.seed(random_state)
        
        selected_question_ids = np.random.choice(question_ids, size=n, replace=False).tolist()
        return self._sample_by_question_ids(selected_question_ids)
    
    def stratified_sample(self, column: str, n: Optional[int] = None, 
                          ratio: Optional[float] = None,
                          strategy: str = 'proportional',
                          random_state: Optional[int] = None) -> pd.DataFrame:
        """
        分层抽取：根据指定列进行分层抽样（在question_id级别，保证多轮对话完整）
        
        Args:
            column: 用于分层的列名
            n: 总抽取的question_id数量（与ratio二选一，注意：实际抽取的行数可能大于n）
            ratio: 总抽取比例（0-1之间，与n二选一），基于question_id数量
            strategy: 抽取策略
                - 'proportional': 按比例抽取（每层按其在总体中的比例抽取）
                - 'equal': 等量抽取（每层抽取相同数量的question_id）
            random_state: 随机种子
        
        Returns:
            抽取的数据
        """
        if column not in self.df.columns:
            raise ValueError(f"列 '{column}' 不存在。可用列: {list(self.df.columns)}")
        
        if n is None and ratio is None:
            raise ValueError("必须指定 n（数量）或 ratio（比例）")
        
        if random_state is not None:
            np.random.seed(random_state)
        
        groups = self._get_question_id_groups()
        
        # 为每个question_id确定其分层值（取该question_id的第一行的值）
        question_id_to_stratum = {}
        for qid, indices in groups.items():
            # 取该question_id的第一行来确定分层值
            first_idx = indices[0]
            question_id_to_stratum[qid] = self.df.loc[first_idx, column]
        
        # 按分层值对question_id进行分组
        stratum_to_question_ids = {}
        for qid, stratum_value in question_id_to_stratum.items():
            if stratum_value not in stratum_to_question_ids:
                stratum_to_question_ids[stratum_value] = []
            stratum_to_question_ids[stratum_value].append(qid)
        
        total_questions = len(groups)
        
        if n is None:
            n = int(total_questions * ratio)
        
        sampled_question_ids = []
        
        if strategy == 'proportional':
            # 按比例抽取
            for stratum_value, qids in stratum_to_question_ids.items():
                layer_ratio = len(qids) / total_questions
                layer_n = max(1, int(n * layer_ratio))  # 至少抽取1个question_id
                layer_n = min(layer_n, len(qids))  # 不超过该层的question_id总数
                
                selected = np.random.choice(qids, size=layer_n, replace=False).tolist()
                sampled_question_ids.extend(selected)
        
        elif strategy == 'equal':
            # 等量抽取
            n_per_layer = max(1, n // len(stratum_to_question_ids))
            for stratum_value, qids in stratum_to_question_ids.items():
                layer_n = min(n_per_layer, len(qids))
                selected = np.random.choice(qids, size=layer_n, replace=False).tolist()
                sampled_question_ids.extend(selected)
        
        else:
            raise ValueError(f"未知的策略: {strategy}。支持: 'proportional', 'equal'")
        
        result = self._sample_by_question_ids(sampled_question_ids)
        # 打乱顺序
        result = result.sample(frac=1, random_state=random_state).reset_index(drop=True)
        
        return result
    
    def custom_stratified_sample(self, column: str, custom_dict: Dict[str, Union[int, float]],
                                random_state: Optional[int] = None) -> pd.DataFrame:
        """
        自定义分层抽取：为每层指定具体的抽取数量或比例（在question_id级别，保证多轮对话完整）
        
        Args:
            column: 用于分层的列名
            custom_dict: 字典，键为列的值，值为抽取的question_id数量（int）或比例（float，0-1之间）
            random_state: 随机种子
        
        Returns:
            抽取的数据
        """
        if column not in self.df.columns:
            raise ValueError(f"列 '{column}' 不存在。可用列: {list(self.df.columns)}")
        
        if random_state is not None:
            np.random.seed(random_state)
        
        groups = self._get_question_id_groups()
        
        # 为每个question_id确定其分层值（取该question_id的第一行的值）
        question_id_to_stratum = {}
        for qid, indices in groups.items():
            first_idx = indices[0]
            question_id_to_stratum[qid] = self.df.loc[first_idx, column]
        
        # 按分层值对question_id进行分组
        stratum_to_question_ids = {}
        for qid, stratum_value in question_id_to_stratum.items():
            if stratum_value not in stratum_to_question_ids:
                stratum_to_question_ids[stratum_value] = []
            stratum_to_question_ids[stratum_value].append(qid)
        
        sampled_question_ids = []
        
        for value, sample_spec in custom_dict.items():
            if value not in stratum_to_question_ids:
                print(f"警告: 值 '{value}' 在数据中不存在，跳过")
                continue
            
            qids = stratum_to_question_ids[value]
            layer_question_count = len(qids)
            
            # 判断是数量还是比例
            if isinstance(sample_spec, int):
                layer_n = min(sample_spec, layer_question_count)
            elif isinstance(sample_spec, float):
                layer_n = max(1, int(layer_question_count * sample_spec))
                layer_n = min(layer_n, layer_question_count)
            else:
                raise ValueError(f"custom_dict的值必须是int（数量）或float（比例），但得到: {type(sample_spec)}")
            
            if layer_n >= layer_question_count:
                sampled_question_ids.extend(qids)
            else:
                selected = np.random.choice(qids, size=layer_n, replace=False).tolist()
                sampled_question_ids.extend(selected)
        
        result = self._sample_by_question_ids(sampled_question_ids)
        # 打乱顺序
        result = result.sample(frac=1, random_state=random_state).reset_index(drop=True)
        
        return result
    
    def show_column_info(self, column: Optional[str] = None):
        """
        显示列的信息
        
        Args:
            column: 列名，如果指定则显示该列的统计信息
        """
        if column:
            if column not in self.df.columns:
                print(f"列 '{column}' 不存在")
                return
            print(f"\n列 '{column}' 的统计信息:")
            print(self.df[column].value_counts())
            print(f"\n唯一值数量: {self.df[column].nunique()}")
        else:
            print("\n所有列的信息:")
            for col in self.df.columns:
                print(f"\n{col}:")
                print(f"  类型: {self.df[col].dtype}")
                print(f"  唯一值数量: {self.df[col].nunique()}")
                if self.df[col].nunique() <= 20:
                    print(f"  值分布: {self.df[col].value_counts().to_dict()}")


def main():
    parser = argparse.ArgumentParser(description='数据抽取工具')
    parser.add_argument('input_file', type=str, help='输入Excel文件路径')
    parser.add_argument('output_file', type=str, help='输出Excel文件路径')
    parser.add_argument('--sheet', type=str, default=0, help='工作表名称或索引（默认: 0）')
    parser.add_argument('--method', type=str, 
                       choices=['uniform', 'random', 'stratified', 'custom'],
                       required=True, help='抽取方法')
    
    # 抽取参数
    parser.add_argument('--n', type=int, help='抽取数量')
    parser.add_argument('--ratio', type=float, help='抽取比例（0-1之间）')
    
    # 分层抽取参数
    parser.add_argument('--column', type=str, help='用于分层的列名（stratified和custom方法需要）')
    parser.add_argument('--strategy', type=str, 
                       choices=['proportional', 'equal'],
                       default='proportional',
                       help='分层抽取策略（proportional: 按比例, equal: 等量）')
    
    # 自定义分层抽取参数（格式: "值1:数量1,值2:数量2" 或 "值1:比例1,值2:比例2"）
    parser.add_argument('--custom', type=str, 
                       help='自定义分层抽取配置，格式: "值1:数量1,值2:数量2" 或 "值1:比例1,值2:比例2"')
    
    # 其他参数
    parser.add_argument('--random_state', type=int, help='随机种子')
    parser.add_argument('--show_info', action='store_true', help='显示数据信息')
    parser.add_argument('--show_column', type=str, help='显示指定列的统计信息')
    
    args = parser.parse_args()
    
    # 创建抽取器
    sampler = DataSampler(args.input_file, sheet_name=args.sheet)
    
    # 显示信息
    if args.show_info:
        sampler.show_column_info()
    
    if args.show_column:
        sampler.show_column_info(args.show_column)
    
    # 执行抽取
    if args.method == 'uniform':
        if args.n is None:
            print("错误: uniform方法需要指定 --n 参数")
            return
        result = sampler.uniform_sample(args.n, random_state=args.random_state)
    
    elif args.method == 'random':
        result = sampler.random_sample(n=args.n, ratio=args.ratio, 
                                      random_state=args.random_state)
    
    elif args.method == 'stratified':
        if args.column is None:
            print("错误: stratified方法需要指定 --column 参数")
            return
        result = sampler.stratified_sample(args.column, n=args.n, ratio=args.ratio,
                                          strategy=args.strategy,
                                          random_state=args.random_state)
    
    elif args.method == 'custom':
        if args.column is None or args.custom is None:
            print("错误: custom方法需要指定 --column 和 --custom 参数")
            return
        # 解析custom参数
        custom_dict = {}
        for item in args.custom.split(','):
            key, value = item.split(':')
            # 尝试转换为int，如果失败则转换为float
            try:
                value = int(value)
            except ValueError:
                value = float(value)
            custom_dict[key] = value
        result = sampler.custom_stratified_sample(args.column, custom_dict,
                                                  random_state=args.random_state)
    
    # 保存结果
    result.to_excel(args.output_file, index=False)
    print(f"\n抽取完成！")
    print(f"原始数据: {len(sampler.df)} 行")
    print(f"抽取数据: {len(result)} 行")
    print(f"结果已保存到: {args.output_file}")


if __name__ == '__main__':
    main()

