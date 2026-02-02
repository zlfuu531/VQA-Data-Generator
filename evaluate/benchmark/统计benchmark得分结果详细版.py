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
    """查找所有finmmr.json和finmmr.jsonl文件"""
    base_path = Path(base_dir)
    result_files = []
    
    # 查找json文件
    for json_file in base_path.rglob("visfineval_sampled_3000.json"):
        result_files.append(json_file)
    
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
        
        # 提取模型名称：优先使用文件路径中的模型名（更准确），否则从by_model中获取
        # 文件路径格式通常是：.../outputs/{profile}/{model_name}/...
        path_parts = file_path_obj.parts
        model_name = file_path_obj.parent.name  # 使用父目录名作为模型名
        
        # 如果父目录名看起来不像模型名，尝试从by_model中获取
        if model_name in ['expert', 'beginner', 'retail', 'outputs'] or not model_name:
            by_model = stats.get('by_model', {})
            model_name = list(by_model.keys())[0] if by_model else model_name
        
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
    """创建Excel报告（转置格式：模型为列，指标为行）"""
    if not data_list:
        print("没有数据可生成报告")
        return
    
    # 创建DataFrame
    df = pd.DataFrame(data_list)
    
    # 处理重复的模型名（添加后缀使其唯一）
    model_name_counts = {}
    unique_model_names = []
    for model_name in df['model_name']:
        if model_name in model_name_counts:
            model_name_counts[model_name] += 1
            unique_name = f"{model_name}_{model_name_counts[model_name]}"
        else:
            model_name_counts[model_name] = 0
            unique_name = model_name
        unique_model_names.append(unique_name)
    
    df['model_name'] = unique_model_names
    
    # 获取模型名称列表
    model_names = df['model_name'].tolist()
    
    # 重新排列列的顺序：模型名、总体统计、各类别统计
    columns_order = ['model_name', 'total_count', 'total_correct', 'total_accuracy']
    
    # 获取所有类别
    categories = set()
    for row in data_list:
        for key in row.keys():
            if key.endswith('_count') and key != 'total_count':
                category = key.replace('_count', '')
                categories.add(category)
    
    # 为每个类别添加列
    for category in sorted(categories):
        columns_order.extend([
            f'{category}_count',
            f'{category}_correct',
            f'{category}_accuracy'
        ])
    
    # 确保所有列都存在
    for col in columns_order:
        if col not in df.columns:
            df[col] = 0
    
    # 重新排列列
    df = df[columns_order]
    
    # 创建指标名称映射（原始列名 -> 显示名称）
    indicator_name_map = {}
    for col in df.columns:
        if col == 'model_name':
            continue
        elif col == 'total_count':
            indicator_name_map[col] = '总题数'
        elif col == 'total_correct':
            indicator_name_map[col] = '总正确数'
        elif col == 'total_accuracy':
            indicator_name_map[col] = '总准确率'
        elif col.endswith('_count'):
            category = col.replace('_count', '')
            if '_' in category:
                parts = category.rsplit('_', 1)
                if len(parts) == 2:
                    category_dim, sub_category = parts
                    indicator_name_map[col] = f'{category_dim}_{sub_category}题数'
                else:
                    indicator_name_map[col] = f'{category}题数'
            else:
                indicator_name_map[col] = f'{category}题数'
        elif col.endswith('_correct'):
            category = col.replace('_correct', '')
            if '_' in category:
                parts = category.rsplit('_', 1)
                if len(parts) == 2:
                    category_dim, sub_category = parts
                    indicator_name_map[col] = f'{category_dim}_{sub_category}正确数'
                else:
                    indicator_name_map[col] = f'{category}正确数'
            else:
                indicator_name_map[col] = f'{category}正确数'
        elif col.endswith('_accuracy'):
            category = col.replace('_accuracy', '')
            if '_' in category:
                parts = category.rsplit('_', 1)
                if len(parts) == 2:
                    category_dim, sub_category = parts
                    indicator_name_map[col] = f'{category_dim}_{sub_category}准确率'
                else:
                    indicator_name_map[col] = f'{category}准确率'
            else:
                indicator_name_map[col] = f'{category}准确率'
        else:
            indicator_name_map[col] = col
    
    # 转置DataFrame：模型作为列，指标作为行
    # 设置模型名为索引，然后转置
    df_transposed = df.set_index('model_name').T
    
    # 创建Excel工作簿
    wb = Workbook()
    ws = wb.active
    ws.title = "模型对比统计"
    
    # 写入表头（第一行：指标名称列 + 各模型名称）
    header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=11)
    
    # 第一列表头
    cell = ws.cell(row=1, column=1, value='指标')
    cell.fill = header_fill
    cell.font = header_font
    cell.alignment = Alignment(horizontal='center', vertical='center')
    
    # 各模型名称作为表头
    for col_idx, model_name in enumerate(model_names, 2):
        cell = ws.cell(row=1, column=col_idx, value=model_name)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', vertical='center')
    
    # 写入数据（转置后的数据）
    bold_font = Font(bold=True)
    normal_font = Font()
    
    for row_idx, (original_col_name, row_values) in enumerate(df_transposed.iterrows(), 2):
        # 获取指标显示名称
        indicator_name = indicator_name_map.get(original_col_name, original_col_name)
        
        # 写入指标名称
        cell = ws.cell(row=row_idx, column=1, value=indicator_name)
        cell.alignment = Alignment(horizontal='left', vertical='center')
        
        # 判断是否为准确率行
        is_accuracy_row = '准确率' in indicator_name
        
        # 写入各模型的数据
        for col_idx, model_name in enumerate(model_names, 2):
            value = row_values[model_name]
            
            # 如果value是Series（由于重复索引），取第一个值
            if isinstance(value, pd.Series):
                value = value.iloc[0]
            
            # 如果是numpy类型，转换为Python原生类型
            if hasattr(value, 'item'):
                value = value.item()
            
            # 保持数值格式（不转换为字符串）
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.alignment = Alignment(horizontal='center', vertical='center')
            
            # 如果是准确率行，加粗字体
            if is_accuracy_row:
                cell.font = bold_font
            else:
                cell.font = normal_font
    
    # 调整列宽
    # 第一列（指标名称列）
    max_indicator_length = max(len(name) for name in indicator_name_map.values()) if indicator_name_map else 10
    ws.column_dimensions['A'].width = min(max_indicator_length + 2, 30)
    
    # 各模型列
    for col_idx, model_name in enumerate(model_names, 2):
        max_length = max(
            len(str(model_name)),
            max(len(str(df_transposed.loc[indicator, model_name])) for indicator in df_transposed.index) if len(df_transposed) > 0 else 0
        )
        adjusted_width = min(max_length + 2, 30)
        ws.column_dimensions[get_column_letter(col_idx)].width = adjusted_width
    
    # 冻结首行和首列
    ws.freeze_panes = 'B2'
    
    # 保存文件
    wb.save(output_file)
    print(f"Excel报告已保存到: {output_file}")

def main():
    base_dir = "/home/zenglingfeng/qa_pipline12-7/evaluate/outputs/expert"
    output_file = "/home/zenglingfeng/qa_pipline12-7/evaluate/benchmark/visfineval-1-8.xlsx"
    
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

