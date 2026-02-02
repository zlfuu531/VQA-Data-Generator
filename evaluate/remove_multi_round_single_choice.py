#!/usr/bin/env python3
"""
删除所有输出文件中 question_type 为 "多轮单选题" 的数据行，并重新计算统计信息
"""
import os
import json
import sys
from pathlib import Path
from typing import List, Dict, Any

# 添加 evaluate_py 目录到路径
evaluate_py_dir = Path(__file__).parent / "evaluate_py"
sys.path.insert(0, str(evaluate_py_dir.parent))

# 导入统计模块
from evaluate_py.statistics import calculate_output_statistics


def process_jsonl_file(file_path: Path) -> bool:
    """
    处理 JSONL 文件：删除 question_type 为 "多轮单选题" 的数据行，并重新计算统计信息
    
    Returns:
        是否进行了修改
    """
    print(f"处理文件: {file_path}")
    
    # 读取所有行
    lines = []
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    if not lines:
        print(f"  文件为空，跳过")
        return False
    
    # 解析第一行（统计信息）
    try:
        first_line = json.loads(lines[0].strip())
        if "statistics" not in first_line:
            print(f"  警告：第一行不是统计信息，跳过")
            return False
    except json.JSONDecodeError:
        print(f"  警告：第一行不是有效的JSON，跳过")
        return False
    
    # 处理数据行（从第二行开始）
    filtered_results = []
    removed_count = 0
    
    for i, line in enumerate(lines[1:], start=2):
        line = line.strip()
        if not line:
            continue
        
        try:
            item = json.loads(line)
            question_type = item.get("question_type", "")
            
            # 如果是多轮单选题，跳过
            if question_type == "多轮单选题":
                removed_count += 1
                continue
            
            filtered_results.append(item)
        except json.JSONDecodeError as e:
            print(f"  警告：第 {i} 行JSON解析失败: {e}，保留该行")
            filtered_results.append(json.loads(line))
    
    if removed_count == 0:
        print(f"  没有找到需要删除的数据，跳过")
        return False
    
    print(f"  删除了 {removed_count} 条多轮单选题数据，剩余 {len(filtered_results)} 条数据")
    
    # 从结果中提取所有模型名称
    enabled_models = set()
    for item in filtered_results:
        # 检查是否有 model 字段
        if "model" in item:
            model_name = item["model"].get("model_name", "")
            if model_name:
                enabled_models.add(model_name)
    
    if not enabled_models:
        # 如果没有找到模型名称，尝试从统计信息中获取
        if "by_model" in first_line.get("statistics", {}):
            enabled_models = set(first_line["statistics"]["by_model"].keys())
    
    if not enabled_models:
        print(f"  警告：无法确定模型名称，使用默认值")
        enabled_models = {"model"}
    
    enabled_models = list(enabled_models)
    
    # 重新计算统计信息
    print(f"  重新计算统计信息（模型: {enabled_models}）...")
    new_statistics = calculate_output_statistics(filtered_results, enabled_models)
    
    # 写入文件
    with open(file_path, 'w', encoding='utf-8') as f:
        # 写入新的统计信息
        first_line["statistics"] = new_statistics
        f.write(json.dumps(first_line, ensure_ascii=False) + '\n')
        
        # 写入过滤后的数据行
        for item in filtered_results:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')
    
    print(f"  ✅ 完成：已更新统计信息并删除多轮单选题数据")
    return True


def process_json_file(file_path: Path) -> bool:
    """
    处理 JSON 文件：删除 question_type 为 "多轮单选题" 的数据项，并重新计算统计信息
    
    Returns:
        是否进行了修改
    """
    print(f"处理文件: {file_path}")
    
    # 读取JSON文件
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"  错误：JSON解析失败: {e}")
        return False
    
    if not isinstance(data, dict) or "results" not in data:
        print(f"  警告：文件格式不正确（缺少 results 字段），跳过")
        return False
    
    # 过滤数据
    original_count = len(data.get("results", []))
    filtered_results = []
    removed_count = 0
    
    for item in data.get("results", []):
        question_type = item.get("question_type", "")
        
        # 如果是多轮单选题，跳过
        if question_type == "多轮单选题":
            removed_count += 1
            continue
        
        filtered_results.append(item)
    
    if removed_count == 0:
        print(f"  没有找到需要删除的数据，跳过")
        return False
    
    print(f"  删除了 {removed_count} 条多轮单选题数据，剩余 {len(filtered_results)} 条数据")
    
    # 从结果中提取所有模型名称
    enabled_models = set()
    for item in filtered_results:
        # 检查是否有 model 字段
        if "model" in item:
            model_name = item["model"].get("model_name", "")
            if model_name:
                enabled_models.add(model_name)
    
    if not enabled_models:
        # 如果没有找到模型名称，尝试从统计信息中获取
        if "statistics" in data and "by_model" in data.get("statistics", {}):
            enabled_models = set(data["statistics"]["by_model"].keys())
    
    if not enabled_models:
        print(f"  警告：无法确定模型名称，使用默认值")
        enabled_models = {"model"}
    
    enabled_models = list(enabled_models)
    
    # 重新计算统计信息
    print(f"  重新计算统计信息（模型: {enabled_models}）...")
    new_statistics = calculate_output_statistics(filtered_results, enabled_models)
    
    # 更新数据
    data["results"] = filtered_results
    data["statistics"] = new_statistics
    
    # 写入文件
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"  ✅ 完成：已更新统计信息并删除多轮单选题数据")
    return True


def main():
    """主函数：遍历目录，处理所有 JSON 和 JSONL 文件"""
    base_dir = Path("/home/zenglingfeng/qa_pipline12-7/evaluate/outputs/expert")
    
    if not base_dir.exists():
        print(f"错误：目录不存在: {base_dir}")
        return
    
    print(f"开始处理目录: {base_dir}")
    print("=" * 80)
    
    # 统计信息
    total_files = 0
    modified_files = 0
    
    # 遍历所有子目录
    for subdir in base_dir.iterdir():
        if not subdir.is_dir():
            continue
        
        print(f"\n处理子目录: {subdir.name}")
        print("-" * 80)
        
        # 查找所有 JSON 和 JSONL 文件
        for file_path in subdir.rglob("*.json"):
            total_files += 1
            if process_json_file(file_path):
                modified_files += 1
        
        for file_path in subdir.rglob("*.jsonl"):
            total_files += 1
            if process_jsonl_file(file_path):
                modified_files += 1
    
    print("\n" + "=" * 80)
    print(f"处理完成！")
    print(f"  总文件数: {total_files}")
    print(f"  修改文件数: {modified_files}")
    print(f"  未修改文件数: {total_files - modified_files}")


if __name__ == "__main__":
    main()
