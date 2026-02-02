#!/usr/bin/env python3
"""
将 VisFinEval TSV 格式转换为 Excel 格式

字段映射：
- index → question_id
- type → image_type
- answer → answer (不变)
- A, B, C, D → options (保留)
- image → image_path
- background_story、information 和 question → question (拼接到一起，不包含选项)
- fintype → fintype (保留)
- md_path → md_path (保留)
- round → round (新增列，相同question_id的不同round放在不同行)
"""

import os
import csv
import pandas as pd
from pathlib import Path
from typing import List, Dict, Any, Optional


def parse_image_path(image_str: str) -> str:
    """
    解析图片路径字符串，支持逗号分隔的多张图片
    
    Args:
        image_str: 图片路径字符串（可能包含逗号分隔的多个路径）
        
    Returns:
        图片路径字符串（逗号分隔）
    """
    if not image_str or not image_str.strip():
        return ""
    
    # 按逗号分隔并清理
    paths = [path.strip() for path in image_str.split(',') if path.strip()]
    return ", ".join(paths)


def build_options_str(row: Dict[str, Any]) -> str:
    """
    构建选项字符串（格式：option_A | option_B | option_C | option_D）
    只处理实际存在且非空的选项列，不会把answer列误当作选项
    
    Args:
        row: TSV行数据
        
    Returns:
        选项字符串
    """
    options = []
    # 只处理A、B、C、D选项，确保这些键存在且值非空
    # 如果TSV文件中没有D列（C列之后直接是answer列），则不会处理D选项
    # 这样就不会把answer列的值误当作D选项
    for opt in ['A', 'B', 'C', 'D']:
        # 明确检查键是否存在（避免把answer列误当作D选项）
        if opt in row:
            value = str(row[opt]).strip() if row[opt] is not None else ""
            # 只有当值非空时才添加选项
            if value:
                options.append(f"option_{opt}: {value}")
    
    return " | ".join(options) if options else ""


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


def convert_row_to_excel_format(row: Dict[str, Any], scenario: str, tsv_filename: str = "") -> Dict[str, Any]:
    """
    转换单行TSV数据为Excel格式
    
    Args:
        row: TSV行数据
        scenario: 场景分类（从文件夹名获取）
        tsv_filename: TSV文件名（用于更细的场景分类）
        
    Returns:
        转换后的数据项（字典格式，用于DataFrame）
    """
    # 构建完整的scenario（包含TSV文件名）
    full_scenario = scenario
    if tsv_filename:
        # 去掉.tsv后缀，添加到scenario中
        tsv_name = Path(tsv_filename).stem
        full_scenario = f"{scenario}::{tsv_name}"
    
    # 获取基础字段，如果为空则保持为空字符串
    index = str(row.get('index', '')) if row.get('index') else ""
    round_val = row.get('round', '').strip() if row.get('round', '').strip() else ""
    
    # 图片路径
    image_str = row.get('image', '').strip() if row.get('image') else ""
    image_path = parse_image_path(image_str) if image_str else ""
    
    # 构建问题（拼接背景信息和补充信息）
    question = build_question(row)
    
    # 获取各个选项，如果TSV文件中没有对应的列，则保持为空字符串
    # 明确检查键是否存在，避免把answer列误当作D选项
    option_A = str(row.get('A', '')).strip() if 'A' in row and row.get('A') else ""
    option_B = str(row.get('B', '')).strip() if 'B' in row and row.get('B') else ""
    option_C = str(row.get('C', '')).strip() if 'C' in row and row.get('C') else ""
    option_D = str(row.get('D', '')).strip() if 'D' in row and row.get('D') else ""
    
    # 构建Excel行数据，所有字段如果为空则保持为空字符串
    excel_row = {
        "question_id": index,
        "round": round_val,
        "scenario": full_scenario,
        "fintype": row.get('fintype', '').strip() if row.get('fintype') else "",
        "image_type": row.get('type', '').strip() if row.get('type') else "",
        "image_path": image_path,
        "md_path": row.get('md_path', '').strip() if row.get('md_path') else "",
        "question": question,
        "option_A": option_A,
        "option_B": option_B,
        "option_C": option_C,
        "option_D": option_D,
        "answer": row.get('answer', '').strip() if row.get('answer') else "",
    }
    
    return excel_row


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


def discover_scenario_folders(base_dir: Path) -> List[str]:
    """
    自动发现包含TSV文件的场景文件夹
    
    Args:
        base_dir: VisFinEval数据目录
        
    Returns:
        场景文件夹名称列表
    """
    scenario_folders = []
    # 需要排除的文件夹（不是场景文件夹）
    exclude_folders = {'data_', 'figure', 'markdown', '__pycache__', '.git'}
    
    if not base_dir.exists():
        print(f"⚠️  数据目录不存在: {base_dir}")
        return scenario_folders
    
    # 遍历数据目录下的所有文件夹
    for item in base_dir.iterdir():
        if item.is_dir() and item.name not in exclude_folders:
            # 检查文件夹中是否有TSV文件
            tsv_files = list(item.glob("*.tsv"))
            if tsv_files:
                scenario_folders.append(item.name)
                print(f"✅ 发现场景文件夹: {item.name} (包含 {len(tsv_files)} 个TSV文件)")
    
    return sorted(scenario_folders)


def process_all_folders(base_dir: Path, scenario_folders: List[str], output_path: Path):
    """
    处理所有文件夹下的TSV文件，合并输出到一个Excel文件
    
    Args:
        base_dir: VisFinEval数据目录
        scenario_folders: 场景文件夹列表（如果为空，则自动发现）
        output_path: 输出Excel文件路径
    """
    all_rows = []
    
    # 如果没有提供场景文件夹列表，则自动发现
    if not scenario_folders:
        print("🔍 自动发现场景文件夹...")
        scenario_folders = discover_scenario_folders(base_dir)
        if not scenario_folders:
            print("⚠️  没有找到包含TSV文件的场景文件夹")
            return
        print(f"   共发现 {len(scenario_folders)} 个场景文件夹\n")
    
    # 遍历所有场景文件夹
    for scenario_folder in scenario_folders:
        folder_path = base_dir / scenario_folder
        
        if not folder_path.exists():
            print(f"⚠️  文件夹不存在: {folder_path}")
            continue
        
        print(f"📁 处理文件夹: {folder_path}")
        
        # 查找所有TSV文件
        tsv_files = sorted(folder_path.glob("*.tsv"))
        
        if not tsv_files:
            print(f"   文件夹 {folder_path} 中没有找到TSV文件")
            continue
        
        print(f"   找到 {len(tsv_files)} 个TSV文件")
        
        # 处理每个TSV文件
        for tsv_file in tsv_files:
            print(f"   📄 处理文件: {tsv_file.name}")
            
            # 加载TSV文件
            rows = load_tsv_file(tsv_file)
            print(f"      读取 {len(rows)} 行数据")
            
            # 转换每一行
            for row in rows:
                excel_row = convert_row_to_excel_format(row, scenario_folder, tsv_file.name)
                all_rows.append(excel_row)
    
    # 转换为DataFrame
    if not all_rows:
        print("⚠️  没有数据可输出")
        return
    
    df = pd.DataFrame(all_rows)
    
    # 将所有列中的空值统一处理为空字符串
    df = df.fillna('')
    
    # 确保round列为字符串类型
    df['round'] = df['round'].astype(str)
    df['round'] = df['round'].replace('nan', '')
    
    # 按question_id和round排序
    df['round_num'] = df['round'].apply(lambda x: int(x) if str(x).strip().isdigit() else 999)
    df = df.sort_values(['question_id', 'round_num'])
    df = df.drop(columns=['round_num'])
    
    # 重新排列列的顺序
    column_order = [
        "question_id",
        "round",
        "scenario",
        "fintype",
        "image_type",
        "image_path",
        "md_path",
        "question",
        "option_A",
        "option_B",
        "option_C",
        "option_D",
        "answer",
    ]
    df = df[column_order]
    
    # 写入Excel文件（na_rep=''确保空值在Excel中显示为空单元格）
    print(f"\n💾 写入输出文件: {output_path}")
    df.to_excel(output_path, index=False, engine='openpyxl', na_rep='')
    
    print(f"✅ 完成！共转换 {len(df)} 行数据")
    print(f"   输出文件: {output_path}\n")


def main():
    """主函数"""
    # 获取脚本所在目录
    script_dir = Path(__file__).parent
    
    # 路径配置
    visfineval_data_dir = Path("/home/zenglingfeng/VisFinEval/data")
    output_path = script_dir / "融合所有问题.xlsx"
    
    # 自动发现场景文件夹（传入空列表表示自动发现）
    # 如果需要手动指定，可以传入文件夹名称列表，例如：
    # scenario_folders = ["Financial Analysis and Business Decision", ...]
    scenario_folders = []
    
    # 处理所有文件夹
    process_all_folders(visfineval_data_dir, scenario_folders, output_path)
    
    print("=" * 60)
    print("🎉 所有转换完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
