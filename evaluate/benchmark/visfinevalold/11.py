#!/usr/bin/env python3
"""
修复版 V4：混合策略
1. 选择题 (3选/4选/多选)：一律读取 A/B/C/D 四列，防止数据错位导致丢失。
2. 非选择题 (判断题/问答题)：强制清空选项列，防止读入脏数据。
"""

import os
import pandas as pd
from pathlib import Path
from typing import List, Dict, Any

# ===================== 题型定义 =====================
INDEX_PREFIX_MAP = {
    '11': ('L1_Q1', '一级题型1'),  # 三选单选题 -> 策略：读 A-D
    '12': ('L1_Q2', '一级题型2'),  # 四选单选题 -> 策略：读 A-D
    '13': ('L1_Q3', '一级题型3'),  # 四选多选题 -> 策略：读 A-D
    '14': ('L1_Q4', '一级题型4'),  # 判断题 -> 策略：【严格不读选项】
    '15': ('L1_Q5', '一级题型5'),  # 四选单选题 -> 策略：读 A-D
    '16': ('L1_Q6', '一级题型6'),  # 四选单选题 -> 策略：读 A-D
    '21': ('L2_Q1', '二级题型1'),  # 三选单选题 -> 策略：读 A-D
    '22': ('L2_Q2', '二级题型2'),  # 四选单选题 -> 策略：读 A-D
    '23': ('L2_Q3', '二级题型3'),  # 四选单选题 -> 策略：读 A-D
    '31': ('L3_Q1', '三级题型1'),  # 四选单选题 -> 策略：读 A-D
    '32': ('L3_Q2', '三级题型2'),  # 四选单选题 -> 策略：读 A-D
    '33': ('L3_Q3', '三级题型3'),  # 四选单选题 -> 策略：读 A-D
    '34': ('L3_Q4', '三级题型4')   # 多轮问答 -> 策略：【严格不读选项】
}

# 定义哪些题型是“完全没有选项”的 (严格模式)
# L1_Q4 = 判断题, L3_Q4 = 问答题
NO_OPTION_TYPES = {'L1_Q4', 'L3_Q4'}

def get_question_type_info(index: str) -> tuple:
    if not index or not str(index).strip():
        return ("", "")
    index_str = str(index).strip()
    if len(index_str) < 2:
        return ("", "")
    prefix = index_str[:2]
    key_name = INDEX_PREFIX_MAP.get(prefix)
    if key_name:
        return key_name
    return ("", "")

def parse_image_path(image_str: str) -> str:
    if not image_str or not str(image_str).strip():
        return ""
    paths = [path.strip() for path in str(image_str).split(',') if path.strip()]
    return ", ".join(paths)

def build_question(row: Dict[str, Any]) -> str:
    parts = []
    def clean(val):
        s = str(val).strip()
        return "" if s.lower() == 'nan' else s

    bg = clean(row.get('background_story', ''))
    if bg: parts.append(f"[背景信息] {bg}")
    
    info = clean(row.get('information', ''))
    if info: parts.append(f"[补充信息] {info}")
    
    q = clean(row.get('question', ''))
    if q: parts.append(q)
    
    return "\n\n".join(parts) if parts else ""

# ===================== 读取逻辑 =====================

def load_tsv_file(tsv_path: Path) -> List[Dict[str, Any]]:
    """
    使用 Python 引擎读取，处理换行和引号
    """
    try:
        # 保持 V2 的 python 引擎逻辑，解决换行和列错位问题
        df = pd.read_csv(
            tsv_path, 
            sep='\t', 
            engine='python',
            dtype=str,
            quotechar='"',
            on_bad_lines='skip' 
        )
        df.columns = [c.strip() for c in df.columns]
        df = df.fillna('')
        return df.to_dict(orient='records')
    except Exception as e:
        print(f"❌ 读取文件严重错误 {tsv_path.name}: {e}")
        return []

def convert_row_to_excel_format(row: Dict[str, Any], scenario: str, tsv_filename: str = "") -> Dict[str, Any]:
    full_scenario = scenario
    if tsv_filename:
        tsv_name = Path(tsv_filename).stem
        full_scenario = f"{scenario}::{tsv_name}"
    
    index = str(row.get('index', '')).strip()
    
    # 获取题型 Key (例如 L1_Q1) 和 名称
    type_key, question_type = get_question_type_info(index)
    
    def get_val(key):
        val = str(row.get(key, '')).strip()
        return val if val and val.lower() != 'nan' else ""

    # === 核心逻辑修改：混合策略 ===
    
    # 默认清空选项
    option_A = ""
    option_B = ""
    option_C = ""
    option_D = ""

    # 逻辑判断：
    # 1. 如果是“无选项题型”(判断题/问答题)，保持为空 (Strict)
    # 2. 其他所有题型 (哪怕是3选题)，都强制读取 A/B/C/D (Relaxed)
    if type_key in NO_OPTION_TYPES:
        # 严格模式：不读选项
        pass 
    else:
        # 宽松模式：读取所有选项
        option_A = get_val('A')
        option_B = get_val('B')
        option_C = get_val('C')
        option_D = get_val('D')

    # 处理 round
    round_raw = str(row.get('round', '')).strip()
    if round_raw.endswith('.0'): round_raw = round_raw[:-2]

    excel_row = {
        "question_id": index,
        "question_type": question_type,
        "round": round_raw,
        "scenario": full_scenario,
        "fintype": get_val('fintype'),
        "image_type": get_val('type'),
        "image_path": parse_image_path(row.get('image', '')),
        "md_path": get_val('md_path'),
        "question": build_question(row),
        "option_A": option_A,
        "option_B": option_B,
        "option_C": option_C,
        "option_D": option_D,
        "answer": get_val('answer'),
    }
    return excel_row

def process_all_folders(base_dir: Path, scenario_folders: List[str], output_path: Path):
    all_rows = []
    
    if not scenario_folders:
        print("🔍 自动发现场景文件夹...")
        exclude_folders = {'data_', 'figure', 'markdown', '__pycache__', '.git', 'scripts'}
        if base_dir.exists():
            for item in base_dir.iterdir():
                if item.is_dir() and item.name not in exclude_folders:
                    if list(item.glob("*.tsv")):
                        scenario_folders.append(item.name)
        scenario_folders.sort()

    for scenario_folder in scenario_folders:
        folder_path = base_dir / scenario_folder
        if not folder_path.exists(): continue
            
        print(f"📁 处理: {folder_path.name}")
        tsv_files = sorted(folder_path.glob("*.tsv"))
        
        for tsv_file in tsv_files:
            rows = load_tsv_file(tsv_file)
            if rows:
                for row in rows:
                    excel_row = convert_row_to_excel_format(row, scenario_folder, tsv_file.name)
                    all_rows.append(excel_row)
    
    if not all_rows:
        print("⚠️  没有数据可输出")
        return
    
    print("\n📦 正在转换为 DataFrame...")
    df = pd.DataFrame(all_rows)
    df = df.fillna('')
    
    print("🔄 正在排序...")
    df['round_sort'] = pd.to_numeric(df['round'], errors='coerce').fillna(0)
    df = df.sort_values(['question_id', 'round_sort'])
    
    column_order = [
        "question_id", "question_type", "round", "scenario", "fintype", 
        "image_type", "image_path", "md_path", "question", 
        "option_A", "option_B", "option_C", "option_D", "answer"
    ]
    
    for col in column_order:
        if col not in df.columns:
            df[col] = ''
            
    df = df[column_order]
    
    print(f"💾 写入输出文件: {output_path}")
    df.to_excel(output_path, index=False, engine='openpyxl')
    print(f"✅ 完成！共转换 {len(df)} 行数据")

def main():
    script_dir = Path(__file__).parent
    # 路径请确认
    visfineval_data_dir = Path("/home/zenglingfeng/VisFinEval/data")
    output_path = script_dir / "VisFinEval_Merged_Hybrid.xlsx"
    
    process_all_folders(visfineval_data_dir, [], output_path)

if __name__ == "__main__":
    main()