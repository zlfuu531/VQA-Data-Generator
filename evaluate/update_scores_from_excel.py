#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 Excel 文件中读取已处理的得分，完全同步到 JSONL 文件中
- Excel 中有的，JSONL 中必须有（补齐缺失的）
- Excel 中没有的，JSONL 中删除
- 完全以 Excel 为准
"""

import json
import pandas as pd
import sys
from pathlib import Path

def read_excel_data(excel_path):
    """读取 Excel 文件中所有有 claude 得分的数据"""
    print(f"正在读取 Excel 文件: {excel_path}")
    df = pd.read_excel(excel_path)
    
    model_col = 'claude-sonnet-4-5-20250929'
    
    if model_col not in df.columns:
        print(f"错误: Excel 文件中未找到列 '{model_col}'")
        return None
    
    # 筛选出有得分（非空且非 NaN）的记录
    df_with_scores = df[df[model_col].notna()].copy()
    
    print(f"Excel 文件总行数: {len(df)}")
    print(f"有 claude 得分的记录数: {len(df_with_scores)}")
    print(f"\nExcel 文件列名: {df.columns.tolist()}")
    
    # 构建数据字典（处理重复的 question_id）
    excel_data = {}
    duplicate_qids = {}
    
    for _, row in df_with_scores.iterrows():
        qid = str(row['question_id']).strip()
        score = row[model_col]
        
        # 转换为布尔值
        if pd.isna(score):
            continue
        
        if isinstance(score, bool):
            match_gt = score
        elif isinstance(score, (int, float)):
            match_gt = bool(score)
        elif isinstance(score, str):
            score_lower = score.lower().strip()
            if score_lower in ['true', '1', 'yes', '是', '正确', '匹配']:
                match_gt = True
            elif score_lower in ['false', '0', 'no', '否', '错误', '不匹配']:
                match_gt = False
            else:
                print(f"警告: 无法解析得分 '{score}' for question_id '{qid}'")
                continue
        else:
            match_gt = bool(score)
        
        # 检查是否有重复的 question_id
        if qid in excel_data:
            if qid not in duplicate_qids:
                duplicate_qids[qid] = [excel_data[qid]['match_gt']]
            duplicate_qids[qid].append(match_gt)
            # 如果有重复，使用最后一个值（或者可以改为使用第一个值）
            print(f"警告: question_id '{qid}' 在 Excel 中重复出现，使用最后一个得分值: {match_gt}")
        
        excel_data[qid] = {
            'question_id': qid,
            'match_gt': match_gt,
            'question': row.get('question', ''),
            'answer': row.get('answer', ''),
            'profile': row.get('profile', 'expert'),
            'question_type': row.get('question_type', ''),
            'image_type': row.get('image_type', ''),
            'difficulty': row.get('difficulty', ''),
            'language': row.get('language', ''),
        }
    
    if duplicate_qids:
        print(f"\n警告: 发现 {len(duplicate_qids)} 个重复的 question_id")
        print("前10个重复的 question_id 及其得分值:")
        for i, (qid, scores) in enumerate(list(duplicate_qids.items())[:10]):
            print(f"  {qid}: {scores} -> 最终使用: {excel_data[qid]['match_gt']}")
    
    print(f"\n成功读取 {len(excel_data)} 条有效得分记录")
    return excel_data

def read_existing_jsonl(jsonl_path):
    """读取现有的 JSONL 文件"""
    print(f"\n正在读取现有 JSONL 文件: {jsonl_path}")
    
    existing_data = {}
    statistics_line = None
    
    with open(jsonl_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            
            try:
                data = json.loads(line)
                
                # 保存第一行的 statistics
                if 'statistics' in data and 'question_id' not in data:
                    statistics_line = line
                    continue
                
                qid = data.get('question_id', '')
                if qid:
                    existing_data[qid] = data
            except json.JSONDecodeError as e:
                print(f"警告: 跳过无效的 JSON 行 {line_num}: {e}")
    
    print(f"现有 JSONL 记录数: {len(existing_data)}")
    return existing_data, statistics_line

def create_jsonl_record(qid, excel_info, existing_record=None):
    """创建或更新 JSONL 记录"""
    model_name = "claude-sonnet-4-5-20250929"
    
    # 如果已有记录，尽量保留原有信息
    if existing_record:
        record = existing_record.copy()
        
        # 更新 match_gt
        if 'model' not in record:
            record['model'] = {}
        record['model']['match_gt'] = excel_info['match_gt']
        record['model']['model_name'] = model_name
        
        # 如果 answer 缺失，设置为"回答缺失但存在"
        if 'answer' not in record.get('model', {}) or not record['model'].get('answer'):
            record['model']['answer'] = "回答缺失但存在"
        
        # 确保其他必要字段存在
        if 'process' not in record.get('model', {}):
            record['model']['process'] = record['model'].get('answer', '')
        if 'response_time' not in record.get('model', {}):
            record['model']['response_time'] = 0.0
        if 'judge_reasoning' not in record.get('model', {}):
            record['model']['judge_reasoning'] = ""
        
        # 更新 profile（如果 Excel 中有）
        if excel_info.get('profile'):
            record['profile'] = excel_info['profile']
    else:
        # 创建新记录
        record = {
            'question_id': qid,
            'profile': excel_info.get('profile', 'expert'),
            'model': {
                'model_name': model_name,
                'answer': excel_info.get('answer') or "回答缺失但存在",
                'process': excel_info.get('answer') or "回答缺失但存在",
                'match_gt': excel_info['match_gt'],
                'response_time': 0.0,
                'judge_reasoning': ""
            }
        }
    
    return record

def sync_jsonl_with_excel(excel_path, jsonl_path, backup=True):
    """同步 JSONL 文件与 Excel 文件"""
    # 读取 Excel 数据
    excel_data = read_excel_data(excel_path)
    if excel_data is None:
        return
    
    # 读取现有 JSONL 数据
    existing_data, statistics_line = read_existing_jsonl(jsonl_path)
    
    # 备份原文件
    if backup:
        backup_path = jsonl_path + '.backup'
        print(f"\n创建备份文件: {backup_path}")
        import shutil
        shutil.copy2(jsonl_path, backup_path)
    
    # 构建新的 JSONL 内容
    new_records = []
    updated_count = 0
    created_count = 0
    deleted_count = 0
    
    # 处理 Excel 中的所有记录
    for qid, excel_info in excel_data.items():
        existing_record = existing_data.get(qid)
        
        if existing_record:
            # 更新现有记录
            new_record = create_jsonl_record(qid, excel_info, existing_record)
            updated_count += 1
        else:
            # 创建新记录
            new_record = create_jsonl_record(qid, excel_info, None)
            created_count += 1
        
        new_records.append(new_record)
    
    # 统计被删除的记录（在 JSONL 中但不在 Excel 中）
    excel_qids = set(excel_data.keys())
    jsonl_qids = set(existing_data.keys())
    deleted_qids = jsonl_qids - excel_qids
    deleted_count = len(deleted_qids)
    
    if deleted_count > 0:
        print(f"\n将被删除的记录数: {deleted_count}")
        print(f"前10个被删除的 question_id: {list(deleted_qids)[:10]}")
    
    # 写入新文件
    print(f"\n正在写入更新后的 JSONL 文件...")
    with open(jsonl_path, 'w', encoding='utf-8') as f:
        # 写入 statistics 行（如果有）
        if statistics_line:
            f.write(statistics_line + '\n')
        
        # 写入所有记录
        for record in new_records:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
    
    print(f"\n同步完成:")
    print(f"  Excel 中的记录数: {len(excel_data)}")
    print(f"  更新现有记录: {updated_count}")
    print(f"  创建新记录: {created_count}")
    print(f"  删除记录: {deleted_count}")
    print(f"  最终 JSONL 记录数: {len(new_records)}")

def main():
    excel_path = "/home/zenglingfeng/qa_pipline12-7/evaluate/outputs/last_evaluate12-25new1.xlsx"
    jsonl_path = "/home/zenglingfeng/qa_pipline12-7/evaluate/outputs/expert/claude-sonnet-4-5-20250929/last_evaluate.jsonl"
    
    sync_jsonl_with_excel(excel_path, jsonl_path)

if __name__ == '__main__':
    main()
