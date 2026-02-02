#!/usr/bin/env python3
"""
将 VisFinEval TSV 格式转换为 qa_pipline12-7/evaluate_py 需要的 JSONL 格式

字段映射：
- index → question_id
- type → image_type
- answer → answer (不变)
- A, B, C, D → options (列表格式，三选题不要D)
- image → image_path (列表)
- background_story、information 和 question → question (拼接到一起，不包含选项)
- fintype → scenario (场景分类)
- md_path → md_path (保留)
"""

import os
import json
import csv
from pathlib import Path
from typing import List, Dict, Any, Optional
from collections import defaultdict


def parse_image_path(image_str: str) -> List[str]:
    """
    解析图片路径字符串，支持逗号分隔的多张图片
    
    Args:
        image_str: 图片路径字符串（可能包含逗号分隔的多个路径）
        
    Returns:
        图片路径列表
    """
    if not image_str or not image_str.strip():
        return []
    
    # 按逗号分隔
    paths = [path.strip() for path in image_str.split(',') if path.strip()]
    
    # 确保路径是绝对路径（如果已经是绝对路径则保持不变）
    result = []
    for path in paths:
        if os.path.isabs(path):
            result.append(path)
        else:
            # 如果是相对路径，需要添加前缀（但根据用户要求，TSV中已经是绝对路径）
            result.append(path)
    
    return result


def build_options(row: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """
    构建选项字典（格式：{"A": "选项1", "B": "选项2", ...}）
    
    Args:
        row: TSV行数据
        
    Returns:
        选项字典，如果没有选项则返回None
    """
    options = {}
    for opt in ['A', 'B', 'C', 'D']:
        value = row.get(opt, '').strip()
        if value:
            options[opt] = value
    
    # 如果所有选项都为空，返回None
    if not options:
        return None
    
    return options


def get_question_type_from_index(index: str) -> str:
    """
    根据index的前两位数字判断题型
    
    Args:
        index: 题目索引（如 "110001", "210201"）
        
    Returns:
        题型名称（中文），映射到 evaluate_py 框架能识别的字段
    """
    if not index or len(index) < 2:
        return "单选题"  # 默认
    
    prefix = index[:2]
    
    # VisFinEval 题型映射到 evaluate_py 题型
    # 参考 VisFinEval/scripts/visfineval.py 的 PROMPT_RULES 和 INDEX_PREFIX_MAP
    type_mapping = {
        '11': '单选题',  # L1_Q1: single_choice_abc (三选)
        '12': '单选题',  # L1_Q2: single_choice_abcd (四选)
        '13': '多选题',  # L1_Q3: multi_choice
        '14': '判断题',  # L1_Q4: judgement
        '15': '单选题',  # L1_Q5: multi_choice -> 修正为单选题
        '16': '单选题',  # L1_Q6: trend_single_choice
        '21': '多轮单选题',  # L2_Q1: multi_round_single_choice
        '22': '多轮单选题',  # L2_Q2: multi_round_single_choice
        '23': '单选题',  # L2_Q3: single_choice_with_bg
        '31': '单选题',  # L3_Q1: single_choice_abcd
        '32': '单选题',  # L3_Q2: single_choice_abcd
        '33': '单选题',  # L3_Q3: single_choice_abcd_with_bg
        '34': '问答题',  # L3_Q4: multi_round_qa -> 修正为问答题
    }
    
    return type_mapping.get(prefix, '单选题')  # 默认单选题


def build_question(row: Dict[str, Any]) -> str:
    """
    构建问题文本，拼接背景信息、补充信息和问题本身
    
    Args:
        row: TSV行数据
        
    Returns:
        问题文本（包含背景信息、补充信息和问题本身，不包含选项）
    """
    parts = []
    
    # 添加背景信息
    background_story = row.get('background_story', '').strip()
    if background_story:
        parts.append(f"[背景信息] {background_story}")
    
    # 添加补充信息
    information = row.get('information', '').strip()
    if information:
        parts.append(f"[补充信息] {information}")
    
    # 添加问题本身
    question = row.get('question', '').strip()
    if question:
        parts.append(question)
    
    return "\n\n".join(parts) if parts else ""


def convert_single_row(row: Dict[str, Any], scenario: str, tsv_filename: str = "") -> Dict[str, Any]:
    """
    转换单行TSV数据为标准格式
    
    Args:
        row: TSV行数据
        scenario: 场景分类（从文件夹名获取）
        tsv_filename: TSV文件名（用于更细的场景分类）
        
    Returns:
        转换后的数据项
    """
    # 构建完整的scenario（包含TSV文件名）
    full_scenario = scenario
    if tsv_filename:
        # 去掉.tsv后缀，添加到scenario中
        tsv_name = Path(tsv_filename).stem
        full_scenario = f"{scenario}::{tsv_name}"
    
    # 获取index并判断题型
    index = str(row.get('index', ''))
    question_type = get_question_type_from_index(index)
    
    # 基础字段
    item = {
        "question_id": index,
        "image_type": row.get('type', ''),
        "question_type": question_type,
        "scenario": full_scenario,
    }
    
    # 图片路径
    image_str = row.get('image', '').strip()
    image_paths = parse_image_path(image_str)
    if image_paths:
        item["image_path"] = image_paths if len(image_paths) > 1 else image_paths[0]
    else:
        item["image_path"] = ""
    
    # md_path（如果有）
    md_path = row.get('md_path', '').strip()
    if md_path:
        item["md_path"] = md_path
    
    # 问题（拼接背景信息和补充信息）
    item["question"] = build_question(row)
    
    # 选项
    options = build_options(row)
    if options:
        item["options"] = options
    
    # 答案
    answer = row.get('answer', '').strip()
    if answer:
        item["answer"] = answer
    
    # fintype（保留作为额外信息）
    fintype = row.get('fintype', '').strip()
    if fintype:
        item["fintype"] = fintype
    
    return item


def group_by_index(rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    按index分组，用于处理多轮题目
    
    Args:
        rows: 所有行数据
        
    Returns:
        按index分组的字典
    """
    grouped = defaultdict(list)
    for row in rows:
        index = str(row.get('index', ''))
        if index:
            grouped[index].append(row)
    
    # 对每个index下的行按round排序
    for index in grouped:
        rows_for_index = grouped[index]
        # 按round排序（如果round为空或无法解析，放在最后）
        rows_for_index.sort(key=lambda r: (
            int(r.get('round', 0)) if r.get('round', '').strip() and r.get('round', '').strip().isdigit() else 999,
            r.get('round', '')
        ))
    
    return grouped


def convert_multi_round(grouped_rows: List[Dict[str, Any]], scenario: str, tsv_filename: str = "") -> Dict[str, Any]:
    """
    转换多轮题目为标准格式
    
    Args:
        grouped_rows: 同一index下的所有行（已按round排序）
        scenario: 场景分类（从文件夹名获取）
        tsv_filename: TSV文件名（用于更细的场景分类）
        
    Returns:
        转换后的多轮题目数据项
    """
    if not grouped_rows:
        return {}
    
    # 构建完整的scenario（包含TSV文件名）
    full_scenario = scenario
    if tsv_filename:
        # 去掉.tsv后缀，添加到scenario中
        tsv_name = Path(tsv_filename).stem
        full_scenario = f"{scenario}::{tsv_name}"
    
    # 使用第一行的基础信息
    first_row = grouped_rows[0]
    index = str(first_row.get('index', ''))
    question_type = get_question_type_from_index(index)
    
    item = {
        "question_id": index,
        "image_type": first_row.get('type', ''),
        "question_type": question_type,
        "scenario": full_scenario,
    }
    
    # 图片路径（从第一行获取，多轮题目通常共用图片）
    image_str = first_row.get('image', '').strip()
    image_paths = parse_image_path(image_str)
    if image_paths:
        item["image_path"] = image_paths if len(image_paths) > 1 else image_paths[0]
    else:
        item["image_path"] = ""
    
    # md_path（如果有）
    md_path = first_row.get('md_path', '').strip()
    if md_path:
        item["md_path"] = md_path
    
    # fintype（保留）
    fintype = first_row.get('fintype', '').strip()
    if fintype:
        item["fintype"] = fintype
    
    # 多轮问题和答案
    question_dict = {}
    answer_dict = {}
    options_dict = {}
    
    for row in grouped_rows:
        # 使用原始的round值作为key，确保按原始顺序排列
        round_val = row.get('round', '').strip()
        if not round_val:
            # 如果round为空，使用索引作为fallback
            round_key = f"round{len(question_dict) + 1}"
        else:
            # 使用原始round值，格式为 "round{原始值}"
            round_key = f"round{round_val}"
        
        # 问题
        question_text = build_question(row)
        if question_text:
            question_dict[round_key] = question_text
        
        # 答案
        answer = row.get('answer', '').strip()
        if answer:
            answer_dict[round_key] = answer
        
        # 选项
        options = build_options(row)
        if options:
            options_dict[round_key] = options
    
    # 设置多轮格式
    if len(question_dict) > 1:
        item["question"] = question_dict
        if answer_dict:
            item["answer"] = answer_dict
        if options_dict:
            item["options"] = options_dict
    else:
        # 只有一轮，使用单轮格式
        if question_dict:
            item["question"] = list(question_dict.values())[0]
        if answer_dict:
            item["answer"] = list(answer_dict.values())[0]
        if options_dict:
            item["options"] = list(options_dict.values())[0]
    
    return item


def load_tsv_file(tsv_path: Path) -> List[Dict[str, Any]]:
    """
    加载TSV文件
    
    Args:
        tsv_path: TSV文件路径
        
    Returns:
        行数据列表
    """
    rows = []
    with open(tsv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter='\t')
        for row in reader:
            rows.append(row)
    return rows


def convert_tsv_folder(folder_path: Path, output_path: Path, scenario_name: str):
    """
    转换文件夹下的所有TSV文件到一个JSONL文件
    
    Args:
        folder_path: 包含TSV文件的文件夹路径
        output_path: 输出JSONL文件路径
        scenario_name: 场景名称（用于scenario字段）
    """
    # 查找所有TSV文件
    tsv_files = sorted(folder_path.glob("*.tsv"))
    
    if not tsv_files:
        print(f"⚠️  文件夹 {folder_path} 中没有找到TSV文件")
        return
    
    print(f"📁 处理文件夹: {folder_path}")
    print(f"   找到 {len(tsv_files)} 个TSV文件")
    
    all_items = []
    
    for tsv_file in tsv_files:
        print(f"   📄 处理文件: {tsv_file.name}")
        
        # 加载TSV文件
        rows = load_tsv_file(tsv_file)
        print(f"      读取 {len(rows)} 行数据")
        
        # 按index分组（处理多轮题目）
        grouped = group_by_index(rows)
        
        # 转换每个分组
        for index, grouped_rows in grouped.items():
            if len(grouped_rows) > 1:
                # 多轮题目
                item = convert_multi_round(grouped_rows, scenario_name, tsv_file.name)
            else:
                # 单轮题目
                item = convert_single_row(grouped_rows[0], scenario_name, tsv_file.name)
            
            if item:
                all_items.append(item)
        
        print(f"      转换后得到 {len(grouped)} 个题目")
    
    # 写入JSONL文件
    print(f"\n💾 写入输出文件: {output_path}")
    with open(output_path, 'w', encoding='utf-8') as f:
        for item in all_items:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')
    
    print(f"✅ 完成！共转换 {len(all_items)} 个题目")
    print(f"   输出文件: {output_path}\n")


def main():
    """主函数"""
    # 路径配置
    visfineval_data_dir = Path("/home/zenglingfeng/VisFinEval/data")
    output_dir = Path("/home/zenglingfeng/qa_pipline12-7/evaluate/benchmark/visfineval")
    
    # 创建输出目录
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 三个场景文件夹
    scenario_folders = [
        "Financial Analysis and Business Decision",
        "Financial Knowledge and Data Analysis",
        "Financial Risk Control and Asset Optimization",
    ]
    
    # 处理每个场景文件夹
    for scenario_folder in scenario_folders:
        folder_path = visfineval_data_dir / scenario_folder
        
        if not folder_path.exists():
            print(f"⚠️  文件夹不存在: {folder_path}")
            continue
        
        # 生成输出文件名（使用文件夹名，替换空格为下划线）
        output_filename = scenario_folder.replace(' ', '_') + ".jsonl"
        output_path = output_dir / output_filename
        
        # 转换
        convert_tsv_folder(folder_path, output_path, scenario_folder)
    
    print("=" * 60)
    print("🎉 所有转换完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()

