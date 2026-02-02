#!/usr/bin/env python3
"""
过滤 FinMMR 数据：
1. 删除所有 scenario 为 "validation" 的数据
2. 只保留 scenario 为 "test" 的数据
3. 删除 image_path 为空的数据
4. 保存到新文件
"""
import json
from pathlib import Path


def is_image_path_empty(image_path):
    """
    检查 image_path 是否为空
    
    Args:
        image_path: 可能是列表、字符串、None等
        
    Returns:
        True 如果为空，False 如果不为空
    """
    if image_path is None:
        return True
    
    if isinstance(image_path, list):
        # 列表：检查是否为空或所有元素都为空
        if len(image_path) == 0:
            return True
        # 检查所有元素是否都为空字符串或None
        return all(not item or (isinstance(item, str) and not item.strip()) for item in image_path)
    
    if isinstance(image_path, str):
        # 字符串：检查是否为空
        return not image_path.strip()
    
    # 其他类型，视为非空
    return False


def main():
    input_file = Path("/home/zenglingfeng/qa_pipline12-7/evaluate/benchmark/finmmr/FinMMR_data_origin.json")
    output_file = Path("/home/zenglingfeng/qa_pipline12-7/evaluate/benchmark/finmmr/FinMMR_data_origin-test.json")
    
    print(f"读取文件: {input_file}")
    
    # 读取JSON文件
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"原始数据条数: {len(data)}")
    
    # 过滤数据
    filtered_data = []
    removed_validation = 0
    removed_empty_image = 0
    
    for item in data:
        # 检查 scenario
        scenario = item.get("scenario", "")
        if scenario == "validation":
            removed_validation += 1
            continue
        
        if scenario != "test":
            # 如果不是 test 也不是 validation，也跳过（只保留 test）
            removed_validation += 1
            continue
        
        # 检查 image_path
        image_path = item.get("image_path")
        if is_image_path_empty(image_path):
            removed_empty_image += 1
            continue
        
        # 保留该数据
        filtered_data.append(item)
    
    print(f"\n过滤结果:")
    print(f"  删除 validation 数据: {removed_validation} 条")
    print(f"  删除 image_path 为空的数据: {removed_empty_image} 条")
    print(f"  保留的数据: {len(filtered_data)} 条")
    
    # 保存到新文件
    print(f"\n保存到: {output_file}")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(filtered_data, f, ensure_ascii=False, indent=2)
    
    print("✅ 完成！")


if __name__ == "__main__":
    main()
