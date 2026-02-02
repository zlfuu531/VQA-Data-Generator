#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统计所有模型的finmme评估结果并生成Excel表格
"""

import json
import os
from pathlib import Path
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter

def find_finmme_result_files(base_dir):
    """查找所有finmme_eval_results.jsonl或json文件"""
    base_path = Path(base_dir)
    result_files = []
    
    # 查找jsonl文件
    for jsonl_file in base_path.rglob("visfineval_sampled_3000.jsonl"):
        result_files.append(jsonl_file)
    
    return result_files

def extract_statistics(file_path):
    """从文件提取统计信息，支持jsonl和json两种格式"""
    try:
        file_path_obj = Path(file_path)
        
        # 根据文件扩展名选择读取方式
        if file_path_obj.suffix == '.jsonl':
            # jsonl格式：每行一个JSON对象，读取第一行
            with open(file_path, 'r', encoding='utf-8') as f:
                first_line = f.readline().strip()
                if not first_line:
                    return None
                data = json.loads(first_line)
        else:
            # json格式：整个文件是一个JSON对象
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        
        stats = data.get('statistics', {})
        
        # 提取模型名称（从by_model中获取第一个模型名）
        by_model = stats.get('by_model', {})
        model_name = list(by_model.keys())[0] if by_model else file_path_obj.parent.name
        
        # 提取总体统计
        total_stats = stats.get('total', {})
        
        # 提取类别统计 - 遍历所有分类维度
        by_category = stats.get('by_category', {})
        
        result = {
            'model_name': model_name,
            'total_count': total_stats.get('total_count', 0),
            'total_correct': total_stats.get('correct_count', 0),
            'total_accuracy': total_stats.get('accuracy', 0.0),
        }
        
        # 遍历所有分类维度（如scenario, difficulty, question_type等）
        for category_dim, category_data in by_category.items():
            if isinstance(category_data, dict):
                # 遍历该维度下的所有子类别
                for sub_category, sub_stats in category_data.items():
                    if isinstance(sub_stats, dict) and 'total_count' in sub_stats:
                        # 使用 维度_子类别 作为键名，避免冲突
                        key_prefix = f'{category_dim}_{sub_category}'
                        result[f'{key_prefix}_count'] = sub_stats.get('total_count', 0)
                        result[f'{key_prefix}_correct'] = sub_stats.get('correct_count', 0)
                        result[f'{key_prefix}_accuracy'] = sub_stats.get('accuracy', 0.0)
        
        return result
    except Exception as e:
        print(f"处理文件 {file_path} 时出错: {e}")
        return None

def create_excel_report(data_list, output_file):
    """创建Excel报告"""
    if not data_list:
        print("没有数据可生成报告")
        return
    
    # 创建DataFrame
    df = pd.DataFrame(data_list)
    
    # 重新排列列的顺序：模型名、总体准确率、各类别准确率
    columns_order = ['model_name', 'total_accuracy']
    
    # 获取所有类别（从accuracy相关的key获取）
    categories = set()
    for row in data_list:
        for key in row.keys():
            if key.endswith('_accuracy') and key != 'total_accuracy':
                category = key.replace('_accuracy', '')
                categories.add(category)
    
    # 为每个类别只添加accuracy列
    for category in sorted(categories):
        columns_order.append(f'{category}_accuracy')
    
    # 确保所有列都存在
    for col in columns_order:
        if col not in df.columns:
            df[col] = 0
    
    # 重新排列列
    df = df[columns_order]
    
    # 创建Excel工作簿
    wb = Workbook()
    ws = wb.active
    ws.title = "模型对比统计"
    
    # 设置表头（只保留准确率列）
    headers = []
    for col in df.columns:
        if col == 'model_name':
            headers.append('模型名称')
        elif col == 'total_accuracy':
            headers.append('总准确率')
        elif col.endswith('_accuracy'):
            category = col.replace('_accuracy', '')
            if '_' in category:
                parts = category.rsplit('_', 1)
                if len(parts) == 2:
                    category_dim, sub_category = parts
                    headers.append(f'{category_dim}_{sub_category}准确率')
                else:
                    headers.append(f'{category}准确率')
            else:
                headers.append(f'{category}准确率')
        else:
            headers.append(col)
    
    # 写入表头
    header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=11)
    
    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', vertical='center')
    
    # 写入数据
    for row_idx, (_, row) in enumerate(df.iterrows(), 2):
        for col_idx, col_name in enumerate(df.columns, 1):
            value = row[col_name]
            if isinstance(value, float):
                if 'accuracy' in col_name:
                    # 准确率显示为百分比，保留2位小数
                    value = f"{value * 100:.2f}%"
                else:
                    value = f"{value:.2f}"
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.alignment = Alignment(horizontal='center', vertical='center')
    
    # 调整列宽
    for col_idx, col_name in enumerate(df.columns, 1):
        max_length = max(
            len(str(headers[col_idx - 1])),
            df[col_name].astype(str).map(len).max() if len(df) > 0 else 0
        )
        adjusted_width = min(max_length + 2, 30)
        ws.column_dimensions[get_column_letter(col_idx)].width = adjusted_width
    
    # 冻结首行
    ws.freeze_panes = 'A2'
    
    # 保存文件
    wb.save(output_file)
    print(f"Excel报告已保存到: {output_file}")

def main():
    base_dir = "/home/zenglingfeng/qa_pipline12-7/evaluate/outputs/expert"
    output_file = "/home/zenglingfeng/qa_pipline12-7/evaluate/benchmark/visfineval模型对比统计.xlsx"
    
    print(f"正在查找 {base_dir} 目录下的所有finmme评估结果文件...")
    result_files = find_finmme_result_files(base_dir)
    
    if not result_files:
        print("未找到任何finmme评估结果文件")
        return
    
    print(f"找到 {len(result_files)} 个文件:")
    for f in result_files:
        print(f"  - {f}")
    
    # 提取所有统计数据
    data_list = []
    for file_path in result_files:
        print(f"\n正在处理: {file_path}")
        stats = extract_statistics(file_path)
        if stats:
            data_list.append(stats)
            print(f"  模型: {stats['model_name']}")
            print(f"  总准确率: {stats['total_accuracy']*100:.2f}%")
    
    if data_list:
        print(f"\n共处理 {len(data_list)} 个模型的数据")
        create_excel_report(data_list, output_file)
    else:
        print("未能提取任何有效数据")

if __name__ == "__main__":
    main()

