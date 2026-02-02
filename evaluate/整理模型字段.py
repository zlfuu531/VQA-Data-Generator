#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
整理 jsonl 文件中的模型字段
只保留与父目录模型名对应的 model 字段，删除其他 model1, model2 等字段
"""

import os
import json
import glob
from pathlib import Path

def process_jsonl_file(file_path):
    """
    处理单个 jsonl 文件
    
    Args:
        file_path: jsonl 文件路径
    """
    # 获取父目录名（模型名）
    parent_dir = Path(file_path).parent.name
    model_name = parent_dir
    
    print(f"处理文件: {file_path}")
    print(f"  模型名: {model_name}")
    
    # 读取文件
    lines = []
    modified_count = 0
    skipped_count = 0
    
    with open(file_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                lines.append(line)
                continue
            
            try:
                data = json.loads(line)
                
                # 检查是否已经有 model 字段且没有 model1, model2 等
                has_model_only = 'model' in data and not any(k.startswith('model') and k != 'model' for k in data.keys())
                
                if has_model_only:
                    # 已经有 model 字段且没有其他 model* 字段，跳过
                    lines.append(line)
                    skipped_count += 1
                    continue
                
                # 查找匹配的模型字段
                matched_model_data = None
                model_keys_to_remove = []
                
                # 检查所有 model* 字段
                for key in list(data.keys()):
                    if key.startswith('model'):
                        if key == 'model':
                            # 检查 model 字段中的 model_name 是否匹配
                            if isinstance(data[key], dict) and data[key].get('model_name') == model_name:
                                matched_model_data = data[key]
                                model_keys_to_remove.append(key)
                            elif data[key] == model_name:
                                # 如果 model 字段直接是字符串
                                matched_model_data = {'model_name': model_name}
                                model_keys_to_remove.append(key)
                        elif key.startswith('model') and key != 'model':
                            # model1, model2 等字段
                            if isinstance(data[key], dict) and data[key].get('model_name') == model_name:
                                if matched_model_data is None:
                                    matched_model_data = data[key]
                                model_keys_to_remove.append(key)
                            else:
                                # 不匹配的 model* 字段，标记删除
                                model_keys_to_remove.append(key)
                
                # 如果找到了匹配的模型数据
                if matched_model_data is not None:
                    # 删除所有 model* 字段
                    for key in model_keys_to_remove:
                        del data[key]
                    
                    # 添加统一的 model 字段
                    data['model'] = matched_model_data
                    
                    lines.append(json.dumps(data, ensure_ascii=False) + '\n')
                    modified_count += 1
                else:
                    # 没有找到匹配的模型，保留原样（可能是统计行等）
                    lines.append(line)
                    if any(k.startswith('model') for k in data.keys()):
                        print(f"  警告: 第 {line_num} 行未找到匹配的模型字段")
            
            except json.JSONDecodeError as e:
                print(f"  错误: 第 {line_num} 行 JSON 解析失败: {e}")
                lines.append(line)  # 保留原行
    
    # 写回文件
    if modified_count > 0:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        print(f"  ✓ 已修改 {modified_count} 行，跳过 {skipped_count} 行")
    else:
        print(f"  - 无需修改（跳过 {skipped_count} 行）")

def main():
    """主函数"""
    base_dir = "/home/zenglingfeng/qa_pipline12-7/evaluate/outputs/expert"
    
    print("=" * 60)
    print("整理模型字段脚本")
    print("=" * 60)
    print(f"目标目录: {base_dir}")
    print()
    
    # 查找所有 jsonl 文件
    jsonl_files = glob.glob(os.path.join(base_dir, "**/*.jsonl"), recursive=True)
    
    if not jsonl_files:
        print("未找到 jsonl 文件")
        return
    
    print(f"找到 {len(jsonl_files)} 个 jsonl 文件")
    print("-" * 60)
    
    # 处理每个文件
    for file_path in sorted(jsonl_files):
        try:
            process_jsonl_file(file_path)
        except Exception as e:
            print(f"  错误: 处理文件时出错: {e}")
        print()
    
    print("=" * 60)
    print("处理完成！")

if __name__ == "__main__":
    main()

