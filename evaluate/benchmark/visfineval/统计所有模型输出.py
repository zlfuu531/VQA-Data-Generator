"""
评测结果汇总脚本
将指定profile文件夹下的所有评测结果文件汇总到一个文件中（支持CSV/TSV/Excel格式）
"""
import json
import csv
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Set
import argparse

# 尝试导入pandas（用于Excel格式）
try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    logging.warning("pandas未安装，Excel格式将不可用。可以使用: pip install pandas openpyxl")

# ==================== 可配置的列名列表 ====================
# 在这里选择要保存的列名，如果为None则保存所有列
# 如果指定了列名列表，则只保存列表中的列
# 
# 可用列名包括：
# 基础字段：
#   - question_id: 问题ID
#   - round: 轮次（多轮题目为数字1,2,3...，单轮题目为空）
#   - question: 问题文本
#   - answer: 答案文本
#   - question_type: 题型
#   - image_type: 图片类型
#   - image_path: 图片路径
#   - original_image_path: 原始图片路径
# 选项列：
#   - option_A, option_B, option_C, option_D: 选项A/B/C/D的内容
# 分类字段：
#   - profile: 用户画像
#   - scenario: 场景
#   - capability: 能力
#   - difficulty: 难度
#   - source: 来源
#   - language: 语言
# 模型得分列：
#   - 模型名称（如 GLM-4.6V, qwen-vl-max 等，会自动从数据中提取）
#
# 示例：
# SELECTED_COLUMNS = [
#     "question_id", "round", "question", "answer", 
#     "question_type", "image_type",
#     "option_A", "option_B", "option_C", "option_D",
#     "GLM-4.6V", "qwen-vl-max"
# ]

#SELECTED_COLUMNS: Optional[List[str]] = None  # 设置为None表示保存所有列
SELECTED_COLUMNS = [
    "question_id", "round", "question", "answer", "question_type",
    "image_type", "image_path", "original_image_path", "profile",
    "scenario", "difficulty", "language", "fintype"
    # 注意：所有模型得分列会自动添加到列表末尾，无需手动指定模型名称
    # "option_A", "option_B", "option_C", "option_D",
]

# ==================== 默认配置参数 ====================
# 可以在代码中设置默认值，命令行参数会覆盖这些默认值

# 默认输入目录路径（profile目录）
DEFAULT_PROFILE_DIR: Optional[str] = "/home/zenglingfeng/qa_pipline12-7/evaluate/outputs/expert"
# DEFAULT_PROFILE_DIR = None  # 如果设置为None，则必须通过命令行参数提供

# 默认输出文件路径（None表示使用 {profile_dir}.xlsx）
DEFAULT_OUTPUT_FILE: Optional[str] = "/home/zenglingfeng/qa_pipline12-7/evaluate/benchmark/visfineval/visfineval-1-8.xlsx"
# DEFAULT_OUTPUT_FILE = None  # 如果设置为None，则自动使用 {profile_dir}.xlsx

# 默认输出格式（csv, tsv, xlsx）
DEFAULT_OUTPUT_FORMAT: str = "xlsx"  # 推荐使用xlsx（最安全，支持换行符和特殊字符）

# 默认文件匹配模式（None表示匹配所有*.json和*.jsonl文件）
DEFAULT_FILE_PATTERN: Optional[str] = "visfineval_sampled_3000.jsonl"
# DEFAULT_FILE_PATTERN = "eval*.json"  # 只匹配eval*.json文件

# 是否启用续传功能（如果输出文件已存在，跳过已处理的记录）
DEFAULT_RESUME_ENABLED: bool = True

def load_json(file_path: Path) -> Dict[str, Any]:
    """加载JSON文件"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_jsonl(file_path: Path) -> List[Dict[str, Any]]:
    """加载JSONL文件（第一行是统计信息，跳过）"""
    results = []
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        if not lines:
            return results
        
        # 跳过第一行（统计信息）
        for line in lines[1:]:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
                results.append(item)
            except json.JSONDecodeError as e:
                logging.warning(f"解析JSONL行失败 {file_path}: {e}")
                continue
    
    return results


def collect_results_from_profile_dir(profile_dir: Path, file_pattern: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    从profile目录下收集所有评测结果文件
    
    Args:
        profile_dir: profile目录路径（如 outputs/expert）
        file_pattern: 文件匹配模式（如 "eval*.json"），如果为None则匹配所有.json和.jsonl文件
        
    Returns:
        所有结果项的列表（每个item只包含对应模型文件夹的数据）
    """
    all_results = []
    
    # 遍历所有子文件夹（模型文件夹）
    for model_dir in profile_dir.iterdir():
        if not model_dir.is_dir():
            continue
        
        # 获取模型文件夹名称（即模型名称）
        model_folder_name = model_dir.name
        
        # 查找匹配的文件
        if file_pattern:
            # 根据文件模式的扩展名决定只匹配哪种类型的文件
            if file_pattern.endswith(".jsonl"):
                # 如果模式是jsonl，只匹配jsonl文件
                json_files = []
                jsonl_files = list(model_dir.glob(file_pattern))
            elif file_pattern.endswith(".json"):
                # 如果模式是json，只匹配json文件
                json_files = list(model_dir.glob(file_pattern))
                jsonl_files = []
            else:
                # 如果模式没有明确的扩展名，尝试匹配两种类型（向后兼容）
                json_files = list(model_dir.glob(file_pattern))
                jsonl_pattern = file_pattern.replace(".json", ".jsonl")
                jsonl_files = list(model_dir.glob(jsonl_pattern))
        else:
            # 默认匹配所有json和jsonl文件
            json_files = list(model_dir.glob("*.json"))
            jsonl_files = list(model_dir.glob("*.jsonl"))
        
        for file_path in json_files + jsonl_files:
            try:
                if file_path.suffix == '.jsonl':
                    items = load_jsonl(file_path)
                else:
                    data = load_json(file_path)
                    # 支持两种格式：直接是列表，或包含results字段
                    if isinstance(data, list):
                        items = data
                    elif isinstance(data, dict) and "results" in data:
                        items = data["results"]
                    else:
                        logging.warning(f"无法解析文件格式: {file_path}")
                        continue
                
                # 过滤：只保留该模型文件夹对应的模型数据，移除其他模型的数据
                filtered_items = []
                for item in items:
                    # 创建新的item，只包含基础字段和该模型的数据
                    filtered_item = {}
                    
                    # 复制基础字段（非model字段）
                    for key, value in item.items():
                        if not key.startswith("model"):
                            filtered_item[key] = value
                    
                    # 只保留model_name等于模型文件夹名称的model字段
                    for key in item.keys():
                        if key.startswith("model") and isinstance(item[key], dict):
                            model_data = item[key]
                            model_name = model_data.get("model_name", "")
                            if model_name == model_folder_name:
                                # 找到对应的模型数据，保留该model_key
                                filtered_item[key] = model_data
                                break
                    
                    # 如果找到了对应的模型数据，添加到结果中
                    if any(k.startswith("model") for k in filtered_item.keys()):
                        filtered_items.append(filtered_item)
                    else:
                        # 如果没有找到对应的模型数据，记录警告（可能是数据格式问题）
                        logging.warning(f"在 {file_path} 的 question_id={item.get('question_id', 'unknown')} 中未找到模型 {model_folder_name} 的数据")
                
                # 统计信息
                total_count = len(items)
                filtered_count = len(filtered_items)
                
                # 统计model.answer为空的数量
                empty_answer_count = 0
                valid_answer_count = 0
                unique_question_ids = set()
                
                for item in filtered_items:
                    question_id = item.get("question_id", "")
                    if question_id:
                        unique_question_ids.add(question_id)
                    
                    # 检查model.answer是否为空
                    model_data = None
                    for key in item.keys():
                        if key.startswith("model") and isinstance(item[key], dict):
                            model_data = item[key]
                            break
                    
                    if model_data:
                        model_answer = model_data.get("answer", "")
                        is_empty = (
                            model_answer is None or 
                            model_answer == "" or 
                            (isinstance(model_answer, list) and len(model_answer) == 0) or
                            (isinstance(model_answer, dict) and len(model_answer) == 0)
                        )
                        if is_empty:
                            empty_answer_count += 1
                        else:
                            valid_answer_count += 1
                
                logging.info(f"模型 {model_folder_name}: 原始记录={total_count}, 过滤后={filtered_count}, 去重question_id={len(unique_question_ids)}, model.answer为空={empty_answer_count}, 有效值={valid_answer_count}")
                
                all_results.extend(filtered_items)
            except Exception as e:
                logging.error(f"加载文件失败 {file_path}: {e}")
                continue
    
    return all_results


def extract_base_fields(item: Dict[str, Any]) -> Dict[str, Any]:
    """提取基础字段和分类字段"""
    base_fields = {}
    
    # 基础字段（不包括options，options会单独处理为A/B/C/D列）
    base_field_names = [
        "question_id", "question", "answer", "question_type", 
        "image_type", "image_path", "profile"
    ]
    
    for field in base_field_names:
        if field in item:
            value = item[field]
            # 处理image_path：如果是列表，转换为用分号分隔的字符串（避免与路径中的逗号混淆）
            if field == "image_path" and isinstance(value, list):
                base_fields[field] = "; ".join(str(v) for v in value if v)
            else:
                base_fields[field] = value
        else:
            base_fields[field] = None
    
    # 分类字段（可能不存在）
    category_fields = ["scenario", "capability", "difficulty", "source", "language", "original_image_path"]
    for field in category_fields:
        if field in item:
            value = item[field]
            # 处理original_image_path：如果是列表，转换为用分号分隔的字符串
            if field == "original_image_path" and isinstance(value, list):
                base_fields[field] = "; ".join(str(v) for v in value if v)
            else:
                base_fields[field] = value
        else:
            base_fields[field] = None
    
    return base_fields


def extract_options_columns(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    提取options字段，转换为A, B, C, D四列
    
    Args:
        item: 数据项
        
    Returns:
        包含option_A, option_B, option_C, option_D的字典
    """
    options_cols = {
        "option_A": None,
        "option_B": None,
        "option_C": None,
        "option_D": None
    }
    
    options = item.get("options")
    if options and isinstance(options, dict):
        for key, value in options.items():
            # 提取选项字母（A, B, C, D等）
            option_key = f"option_{key.upper()}"
            if option_key in options_cols:
                options_cols[option_key] = str(value) if value else None
    
    return options_cols


def get_model_names_from_results(results: List[Dict[str, Any]]) -> Set[str]:
    """从结果中提取所有模型名称"""
    model_names = set()
    
    for item in results:
        for key in item.keys():
            if key.startswith("model") and isinstance(item[key], dict):
                model_data = item[key]
                if "model_name" in model_data:
                    model_names.add(model_data["model_name"])
    
    return model_names


def get_match_gt_value(model_data: Dict[str, Any], round_key: Optional[str] = None) -> Optional[int]:
    """
    获取模型的match_gt值（0或1）
    
    Args:
        model_data: 模型数据字典
        round_key: 轮次键（如"round1"），如果是None则处理单轮题目
        
    Returns:
        1表示正确，0表示错误，None表示数据无效
    """
    if not isinstance(model_data, dict):
        return None
    
    match_gt = model_data.get("match_gt")
    
    if match_gt is None:
        return None
    
    # 多轮题目：match_gt是字典
    if isinstance(match_gt, dict):
        if round_key and round_key in match_gt:
            return 1 if match_gt[round_key] else 0
        else:
            # 如果没有指定round_key，返回None（不应该发生）
            return None
    # 单轮题目：match_gt是布尔值
    elif isinstance(match_gt, bool):
        if round_key:
            # 单轮题目不应该有round_key
            return None
        return 1 if match_gt else 0
    else:
        return None


def expand_multi_round_item(item: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    展开多轮题目为多行数据（每轮一行）
    
    Args:
        item: 原始数据项
        
    Returns:
        展开后的数据项列表（每轮一行）
    """
    question = item.get("question", "")
    answer = item.get("answer", "")
    
    # 判断是否为多轮题目
    is_multi_round = isinstance(question, dict) and isinstance(answer, dict)
    
    if not is_multi_round:
        # 单轮题目，直接返回
        return [item]
    
    # 多轮题目：展开为多行
    expanded_items = []
    
    # 获取所有轮次键（按顺序）
    round_keys = sorted(
        [k for k in question.keys() if k.startswith("round")],
        key=lambda x: int(x.replace("round", "")) if x.replace("round", "").isdigit() else 999
    )
    
    for round_key in round_keys:
        # 创建新的数据项（单轮格式）
        new_item = item.copy()
        
        # 提取该轮次的问题和答案
        new_item["question"] = question.get(round_key, "")
        new_item["answer"] = answer.get(round_key, "")
        
        # 添加round字段（转换为数字，如round1 -> 1, round2 -> 2）
        round_num = round_key.replace("round", "")
        new_item["round"] = int(round_num) if round_num.isdigit() else round_key
        
        # 处理选项（如果有）
        options = item.get("options")
        if isinstance(options, dict) and round_key in options:
            new_item["options"] = options[round_key]
        else:
            new_item["options"] = None
        
        # 处理模型字段：提取每轮的match_gt
        for key in list(new_item.keys()):
            if key.startswith("model") and isinstance(new_item[key], dict):
                model_data = new_item[key]
                # 获取该轮次的match_gt值
                match_gt_value = get_match_gt_value(model_data, round_key)
                if match_gt_value is not None:
                    # 将match_gt转换为单轮格式（布尔值）
                    model_data_copy = model_data.copy()
                    model_data_copy["match_gt"] = bool(match_gt_value)
                    new_item[key] = model_data_copy
                else:
                    # 如果无法获取match_gt，标记为False
                    model_data_copy = model_data.copy()
                    model_data_copy["match_gt"] = False
                    new_item[key] = model_data_copy
        
        expanded_items.append(new_item)
    
    return expanded_items


def load_existing_csv_records(output_csv: Path, file_format: str = 'csv') -> Dict[str, Dict[str, Any]]:
    """
    加载已存在的文件中的记录（支持CSV/TSV/Excel）
    
    Args:
        output_csv: 文件路径
        file_format: 文件格式（'csv', 'tsv', 'xlsx'）
    
    Returns:
        字典，key为 (question_id, round) 的元组转换为字符串，value为该行的完整数据（包含所有模型列）
    """
    existing_records = {}
    
    if not output_csv.exists():
        return existing_records
    
    try:
        if file_format == 'xlsx' and PANDAS_AVAILABLE:
            # 使用pandas读取Excel
            df = pd.read_excel(output_csv, engine='openpyxl')
            for _, row in df.iterrows():
                question_id = str(row.get("question_id", ""))
                round_value = row.get("round")
                round_str = str(round_value) if pd.notna(round_value) and round_value != "" else ""
                key = f"{question_id}|||{round_str}"
                existing_records[key] = row.to_dict()
        else:
            # 读取CSV或TSV
            delimiter = '\t' if file_format == 'tsv' else ','
            with open(output_csv, 'r', encoding='utf-8', newline='') as f:
                reader = csv.DictReader(f, delimiter=delimiter)
                for row in reader:
                    question_id = row.get("question_id", "")
                    round_value = row.get("round", "")
                    round_str = str(round_value) if round_value else ""
                    key = f"{question_id}|||{round_str}"
                    existing_records[key] = row
        
        logging.info(f"从现有文件加载了 {len(existing_records)} 条已处理的记录 (格式: {file_format})")
    except Exception as e:
        logging.warning(f"读取现有文件失败 {output_csv}: {e}，将重新生成")
        existing_records = {}
    
    return existing_records


def get_record_key(item: Dict[str, Any]) -> str:
    """
    获取数据项的唯一标识键（行级别，基于question_id和round）
    
    Args:
        item: 展开后的数据项（已包含round字段）
        
    Returns:
        唯一标识键字符串
    """
    question_id = item.get("question_id", "")
    round_value = item.get("round")
    round_str = str(round_value) if round_value is not None else ""
    return f"{question_id}|||{round_str}"


def get_processed_models(existing_row: Dict[str, Any], model_columns: List[str]) -> Set[str]:
    """
    从已存在的行中提取已处理的模型列表
    
    Args:
        existing_row: 已存在的CSV行数据
        model_columns: 所有可能的模型列名列表
        
    Returns:
        已处理的模型名称集合（如果模型列存在且值不为空，则认为已处理）
    """
    processed_models = set()
    for model_name in model_columns:
        if model_name in existing_row:
            value = existing_row[model_name]
            # 如果值存在且不为空字符串，则认为该模型已处理
            if value and str(value).strip():
                processed_models.add(model_name)
    return processed_models


def get_output_format(output_path: Path) -> str:
    """
    根据输出文件扩展名确定输出格式
    
    Returns:
        'csv', 'tsv', 或 'xlsx'
    """
    ext = output_path.suffix.lower()
    if ext == '.xlsx' or ext == '.xls':
        return 'xlsx'
    elif ext == '.tsv':
        return 'tsv'
    else:
        return 'csv'  # 默认CSV


def write_to_csv_tsv(all_rows: List[Dict[str, Any]], csv_columns: List[str], 
                     output_path: Path, format_type: str = 'csv'):
    """
    写入CSV或TSV文件（正确处理换行符和特殊字符）
    
    Args:
        all_rows: 所有行数据
        csv_columns: 列名列表
        output_path: 输出文件路径
        format_type: 'csv' 或 'tsv'
    """
    delimiter = ',' if format_type == 'csv' else '\t'
    
    with open(output_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=csv_columns, delimiter=delimiter, 
                               quoting=csv.QUOTE_MINIMAL, escapechar=None)
        writer.writeheader()
        writer.writerows(all_rows)
    
    logging.info(f"成功写入 {len(all_rows)} 行数据到 {output_path} (格式: {format_type.upper()})")


def clean_illegal_chars(value: Any) -> Any:
    """
    清理openpyxl不允许的非法字符（控制字符，除了换行符、制表符、回车符）
    
    Args:
        value: 要清理的值
        
    Returns:
        清理后的值
    """
    if not isinstance(value, str):
        return value
    
    # openpyxl不允许的字符：ASCII 0x00-0x1F范围内的控制字符
    # 但允许：\n (0x0A), \r (0x0D), \t (0x09)
    # 需要移除：0x00-0x08, 0x0B-0x0C, 0x0E-0x1F
    cleaned = []
    for char in value:
        code = ord(char)
        # 允许的字符：普通字符（>=32）、换行符(\n=10)、制表符(\t=9)、回车符(\r=13)
        if code >= 32 or code in (9, 10, 13):
            cleaned.append(char)
        # 其他控制字符直接跳过（不添加）
    
    return ''.join(cleaned)


def write_to_excel(all_rows: List[Dict[str, Any]], csv_columns: List[str], 
                   output_path: Path):
    """
    写入Excel文件（最安全，完美支持换行符和特殊字符）
    
    Args:
        all_rows: 所有行数据
        csv_columns: 列名列表
        output_path: 输出文件路径
    
    注意：空字符串会保持为空白单元格（不转换为NaN或0），这符合预期行为
    """
    if not PANDAS_AVAILABLE:
        raise ImportError("pandas未安装，无法使用Excel格式。请安装: pip install pandas openpyxl")
    
    # 清理所有字符串值中的非法字符（openpyxl不允许某些控制字符）
    cleaned_rows = []
    for row in all_rows:
        cleaned_row = {}
        for key, value in row.items():
            if isinstance(value, str):
                cleaned_row[key] = clean_illegal_chars(value)
            else:
                cleaned_row[key] = value
        cleaned_rows.append(cleaned_row)
    
    # 转换为DataFrame
    df = pd.DataFrame(cleaned_rows, columns=csv_columns)
    
    # 确保空字符串保持为空字符串（不会被pandas自动转换为NaN）
    # 这样在Excel中会显示为空白单元格，而不是NaN或0
    # 注意：这里不需要特殊处理，因为空字符串在pandas中本身就是空字符串，写入Excel时会显示为空白
    
    # 写入Excel（使用openpyxl引擎，确保正确处理空值）
    df.to_excel(output_path, index=False, engine='openpyxl', na_rep='')
    
    logging.info(f"成功写入 {len(df)} 行数据到 {output_path} (格式: Excel)")
    logging.info(f"提示：未检测到的模型结果会显示为空白单元格（而不是0）")


def aggregate_results_to_csv(
    profile_dir: Path, 
    output_csv: Path, 
    file_pattern: Optional[str] = None,
    include_columns: Optional[List[str]] = None,
    default_columns: Optional[List[str]] = None,
    resume: bool = True,
    output_format: Optional[str] = None
):
    """
    汇总评测结果到文件（支持CSV/TSV/Excel格式）
    
    Args:
        profile_dir: profile目录路径（如 outputs/expert）
        output_csv: 输出文件路径
        file_pattern: 文件匹配模式（可选）
        include_columns: 要包含的列列表（如果为None则包含所有列）
        resume: 是否启用续传功能（如果输出文件已存在，跳过已处理的记录）
        output_format: 输出格式（'csv', 'tsv', 'xlsx'），如果为None则根据文件扩展名自动判断
    """
    logging.info(f"开始汇总 {profile_dir} 下的评测结果")
    
    # 确定输出格式（需要先确定，以便检查续传功能）
    if output_format is None:
        output_format = get_output_format(output_csv)
    
    # 如果启用续传功能且输出文件已存在，加载已处理的记录
    existing_records = {}
    if resume and output_csv.exists() and output_format != 'xlsx':
        # Excel格式暂不支持续传（pandas续传比较复杂），会重新生成
        existing_records = load_existing_csv_records(output_csv, output_format)
        if existing_records:
            logging.info(f"续传模式：发现 {len(existing_records)} 条已处理的记录，将跳过这些记录")
    
    # 收集所有结果
    all_results = collect_results_from_profile_dir(profile_dir, file_pattern=file_pattern)
    
    if not all_results:
        logging.warning(f"在 {profile_dir} 下没有找到任何评测结果文件")
        return
    
    logging.info(f"共收集到 {len(all_results)} 条结果")
    
    # 展开多轮题目
    expanded_results = []
    for item in all_results:
        expanded = expand_multi_round_item(item)
        expanded_results.extend(expanded)
    
    logging.info(f"展开多轮题目后共 {len(expanded_results)} 行数据")
    
    # 获取所有模型名称（按字母顺序排序，保证列顺序一致）
    model_names = sorted(get_model_names_from_results(expanded_results))
    logging.info(f"找到模型: {model_names}")
    
    # 确定CSV列的顺序（需要提前确定，以便检查已处理的模型）
    base_columns = [
        "question_id", "round", "question", "answer", "question_type",
        "image_type", "image_path", "original_image_path", 
        "option_A", "option_B", "option_C", "option_D",
        "profile", "scenario", "capability", "difficulty", "source", "language"
    ]
    model_columns = model_names
    
    # 如果启用续传且已有记录，需要从已有记录中提取已存在的模型列
    if resume and existing_records:
        # 检查已存在记录中的模型列（可能包含不在当前数据中的模型）
        all_existing_models = set()
        for existing_row in existing_records.values():
            for col_name in existing_row.keys():
                if col_name not in base_columns and col_name:
                    all_existing_models.add(col_name)
        # 合并所有模型列（已存在的 + 新发现的）
        model_columns = sorted(set(model_names) | all_existing_models)
        if all_existing_models:
            logging.info(f"续传模式：发现已存在的模型列: {sorted(all_existing_models)}")
    
    all_columns = base_columns + model_columns
    
    # 第一步：按record_key分组，合并同一问题的所有模型结果
    items_by_key: Dict[str, List[Dict[str, Any]]] = {}
    for item in expanded_results:
        record_key = get_record_key(item)
        if record_key not in items_by_key:
            items_by_key[record_key] = []
        items_by_key[record_key].append(item)
    
    # 第二步：构建CSV行数据（每个record_key只生成一行）
    csv_rows = []
    skipped_models_count = 0
    new_rows_count = 0
    updated_rows_count = 0
    
    for record_key, items in items_by_key.items():
        # 检查是否已存在该记录（行级别）
        existing_row = None
        processed_models = set()
        if resume and existing_records and record_key in existing_records:
            existing_row = existing_records[record_key]
            # 获取已处理的模型列表
            processed_models = get_processed_models(existing_row, model_columns)
        
        # 合并所有items中的模型数据（同一问题的所有模型结果）
        # 如果同一问题有多条记录，使用得分最高的那个（1优先于0）
        all_item_models = {}
        # 使用第一个item的基础字段（同一问题的所有item的基础字段应该相同）
        first_item = items[0]
        
        # 处理每个item：单独检查每个模型的answer是否为空
        # 如果某个模型的model.answer为空，则该模型对于这个问题的得分应该是空值
        # 注意：这里检查的是model.answer（模型答案），不是item["answer"]（标准答案）
        # 记录所有处理过的模型（包括answer为空的），用于续传模式下的更新
        processed_model_names = set()
        
        for item in items:
            # 从item中找出模型数据
            model_data = None
            model_name = None
            for key in item.keys():
                if key.startswith("model") and isinstance(item[key], dict):
                    model_data = item[key]
                    model_name = model_data.get("model_name")
                    break
            
            if not model_data or not model_name:
                continue  # 没有模型数据，跳过
            
            # 记录处理过的模型名称（无论answer是否为空）
            processed_model_names.add(model_name)
            
            # 检查该模型的answer（model.answer）是否为空
            model_answer = model_data.get("answer", "")
            # 判断model.answer是否为空：None、空字符串、空列表、空字典都视为空
            is_model_answer_empty = (
                model_answer is None or 
                model_answer == "" or 
                (isinstance(model_answer, list) and len(model_answer) == 0) or
                (isinstance(model_answer, dict) and len(model_answer) == 0)
            )
            
            # 如果该模型的answer为空，跳过该模型的得分处理
            # 这样该模型对于这个问题的得分就会保持为空（不在all_item_models中）
            if is_model_answer_empty:
                continue  # 跳过这个模型，不处理该模型的得分
            
            # model.answer不为空，正常处理该模型的得分
            match_gt = model_data.get("match_gt", False)
            score = 1 if match_gt else 0
            # 如果已经有更高的得分（1），保持1；否则使用当前得分
            # 这样确保同一问题有多条记录时，优先选择得分最高的（1优先于0）
            if model_name not in all_item_models:
                all_item_models[model_name] = score
            else:
                # 取最大值：如果已有1就保持1，如果当前是1就设置为1
                all_item_models[model_name] = max(all_item_models[model_name], score)
        
        # 检查需要更新的模型（新模型或数据有变化的模型）
        # 注意：如果某个模型的answer为空，它不在all_item_models中，但需要更新为空值
        models_to_update = set()
        if existing_row:
            # 检查所有处理过的模型（包括answer为空的）
            for model_name in processed_model_names:
                if model_name not in processed_models:
                    # 新模型，需要添加（无论answer是否为空）
                    models_to_update.add(model_name)
                elif model_name in all_item_models:
                    # 已存在的模型，且answer不为空，检查数据是否不同
                    new_value = all_item_models[model_name]
                    old_value = existing_row.get(model_name)
                    # 将旧值转换为整数进行比较（处理字符串"0"/"1"的情况）
                    old_value_int = 0
                    if old_value is not None and str(old_value).strip():
                        try:
                            old_value_int = int(str(old_value).strip())
                        except (ValueError, AttributeError):
                            old_value_int = 0
                    
                    if new_value != old_value_int:
                        # 数据不同，需要更新
                        models_to_update.add(model_name)
                else:
                    # 已存在的模型，但answer为空（不在all_item_models中）
                    # 需要检查旧值是否为空，如果不为空则需要更新为空值
                    old_value = existing_row.get(model_name)
                    # 如果旧值不为空（是0或1），需要更新为空值
                    if old_value is not None and str(old_value).strip():
                        models_to_update.add(model_name)
        else:
            # 没有已有行，所有处理过的模型都需要更新（包括answer为空的）
            models_to_update = processed_model_names
        
        # 如果所有模型都已处理过且数据相同，跳过这个记录
        if resume and existing_row and not models_to_update:
            # 统计跳过的模型数量（包括answer为空的模型）
            skipped_models_count += len(processed_model_names)
            continue
        
        # 构建或更新行数据
        if existing_row:
            # 使用已有行作为基础，更新需要更新的模型列
            row = existing_row.copy()
            for model_name in models_to_update:
                # 如果模型有数据，使用数据；如果没有，设为空值（不写0）
                # 重要：
                # - 如果某个模型的answer为空，该模型不会在all_item_models中，得分就是空值
                # - 空值表示该模型没有结果或answer为空，0表示模型答错了
                if model_name in all_item_models:
                    row[model_name] = all_item_models[model_name]  # 有数据：0（错误）或1（正确）
                else:
                    # 如果找不到该模型的数据，设为空字符串（而不是0），表示该模型没有结果或answer为空
                    row[model_name] = ""
            # 确保所有模型列都存在（对于不在当前数据中的模型列，保持原值或设为空值）
            for model_name in model_columns:
                if model_name not in row:
                    row[model_name] = ""
            if models_to_update:
                updated_rows_count += 1
        else:
            # 创建新行
            row = {}
            
            # 提取基础字段（使用第一个item）
            base_fields = extract_base_fields(first_item)
            row.update(base_fields)
            
            # 添加round字段（多轮题目显示为数字1,2,3...，单轮题目为None）
            row["round"] = first_item.get("round")
            
            # 提取options为A/B/C/D列（使用第一个item）
            options_cols = extract_options_columns(first_item)
            row.update(options_cols)
            
            # 为每个模型添加得分列（合并所有items中的模型结果）
            # 重要：
            # 1. 如果某个模型的answer为空，该模型不会在all_item_models中，得分就是空值
            # 2. 如果某个问题的某行没有检测到某个模型的结果，会保持为空字符串 ""（而不是0）
            # 3. 这样可以在Excel/CSV中区分：
            #    - 0 = 模型答错了（有answer且有结果）
            #    - 1 = 模型答对了（有answer且有结果）
            #    - 空 = 没有结果（answer为空 或 该模型没有结果）
            for model_name in model_columns:
                if model_name in all_item_models:
                    # 有数据，使用数据：0（错误）或1（正确）
                    row[model_name] = all_item_models[model_name]
                else:
                    # 如果找不到该模型的数据，设为空字符串（而不是0），表示该模型没有结果或answer为空
                    row[model_name] = ""
            
            new_rows_count += 1
        
        csv_rows.append(row)
    
    if skipped_models_count > 0:
        logging.info(f"续传模式：跳过了 {skipped_models_count} 个已处理的模型结果")
    if updated_rows_count > 0:
        logging.info(f"续传模式：更新了 {updated_rows_count} 行（添加了新模型列）")
    if new_rows_count > 0:
        logging.info(f"续传模式：新增了 {new_rows_count} 行")
    
    # CSV列的顺序已在上面确定（all_columns），这里直接使用
    
    # 确定最终要使用的列
    # 优先级：命令行参数 > 函数参数default_columns > 代码中的SELECTED_COLUMNS > 所有列
    columns_to_use = include_columns or default_columns or SELECTED_COLUMNS
    
    if columns_to_use:
        # 使用指定的列
        valid_columns = []
        specified_model_names = set()  # 用户手动指定的模型名称
        
        for col in columns_to_use:
            if col in all_columns:
                valid_columns.append(col)
            elif col in model_names:
                # 如果是指定的模型名称，记录但不立即添加（后面统一处理）
                specified_model_names.add(col)
            else:
                logging.warning(f"列名 '{col}' 不在可用列中，将被忽略")
        
        # 如果是通过SELECTED_COLUMNS或default_columns指定的（不是命令行参数），自动添加所有模型列
        if not include_columns:
            # 自动添加所有模型列（排除用户已经手动指定的）
            for model_name in model_columns:
                if model_name not in specified_model_names:
                    valid_columns.append(model_name)
        else:
            # 命令行参数：只添加用户明确指定的模型列
            for model_name in sorted(specified_model_names):
                if model_name not in valid_columns:
                    valid_columns.append(model_name)
        
        if not valid_columns:
            logging.warning("指定的列中没有有效列，将使用所有列")
            csv_columns = all_columns
        else:
            csv_columns = valid_columns
            source = "命令行参数" if include_columns else ("函数参数" if default_columns else "代码中的SELECTED_COLUMNS")
            logging.info(f"使用{source}指定的列（已自动添加所有模型列）: {csv_columns}")
    else:
        # 使用所有列
            csv_columns = all_columns
            logging.info(f"使用所有列（共{len(csv_columns)}列）")
    
    # 输出格式已在函数开头确定，这里不需要再次确定
    
    # 验证格式
    if output_format == 'xlsx' and not PANDAS_AVAILABLE:
        logging.error("Excel格式需要pandas和openpyxl，请安装: pip install pandas openpyxl")
        logging.info("将改用CSV格式")
        output_format = 'csv'
        # 修改输出文件扩展名
        output_csv = output_csv.with_suffix('.csv')
    
    # 创建输出目录
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    
    # 如果启用续传且已有记录，需要合并新旧数据
    # 注意：续传功能目前只支持CSV/TSV格式，Excel格式会重新生成
    if resume and existing_records and output_format != 'xlsx':
        # 创建一个映射，将csv_rows按record_key索引（以便替换已存在的行）
        csv_rows_by_key = {}
        for row in csv_rows:
            # 从row字典中提取question_id和round（row可能是从existing_row复制而来，或者是新创建的）
            question_id = row.get("question_id", "")
            round_value = row.get("round")
            round_str = str(round_value) if round_value is not None and round_value != "" else ""
            record_key = f"{question_id}|||{round_str}"
            csv_rows_by_key[record_key] = row
        
        # 合并：已更新的行用新数据替换，未更新的行保留原数据，全新的行添加
        all_rows = []
        processed_keys = set()
        
        # 先处理已存在的记录（用更新后的数据替换，或保留原数据）
        for existing_key, existing_row in existing_records.items():
            if existing_key in csv_rows_by_key:
                # 该行已被更新，使用新数据
                all_rows.append(csv_rows_by_key[existing_key])
            else:
                # 该行未被更新，保留原数据
                all_rows.append(existing_row)
            processed_keys.add(existing_key)
        
        # 再添加全新的行（不在已存在记录中的行）
        for row in csv_rows:
            record_key = get_record_key(row)
            if record_key not in processed_keys:
                all_rows.append(row)
        
        # 写入文件（使用正确的格式）
        if output_format == 'xlsx':
            write_to_excel(all_rows, csv_columns, output_csv)
        else:
            write_to_csv_tsv(all_rows, csv_columns, output_csv, output_format)
    else:
        # 直接写入所有记录（新文件或禁用续传）
        if output_format == 'xlsx':
            write_to_excel(csv_rows, csv_columns, output_csv)
        else:
            write_to_csv_tsv(csv_rows, csv_columns, output_csv, output_format)


def main():
    parser = argparse.ArgumentParser(description='汇总评测结果到文件（支持CSV/TSV/Excel格式）')
    parser.add_argument('profile_dir', type=str, nargs='?', default=DEFAULT_PROFILE_DIR,
                       help=f'Profile目录路径（默认：代码中DEFAULT_PROFILE_DIR设置，当前为: {DEFAULT_PROFILE_DIR}）')
    parser.add_argument('--output', type=str, default=None, 
                       help=f'输出文件路径（默认：代码中DEFAULT_OUTPUT_FILE设置，或{{profile_dir}}.xlsx，当前默认: {DEFAULT_OUTPUT_FILE}）')
    parser.add_argument('--format', type=str, choices=['csv', 'tsv', 'xlsx'], default=None,
                       help=f'输出格式（csv/tsv/xlsx），如果未指定则根据输出文件扩展名自动判断（默认: {DEFAULT_OUTPUT_FORMAT}）')
    parser.add_argument('--pattern', type=str, default=DEFAULT_FILE_PATTERN, 
                       help=f'文件匹配模式（默认：代码中DEFAULT_FILE_PATTERN设置，或所有*.json和*.jsonl文件，例如：eval*.json）')
    parser.add_argument('--columns', type=str, nargs='+', default=None, 
                       help='要包含的列名列表（例如：--columns question_id round question answer GLM-4.6V），如果不指定则使用代码中的SELECTED_COLUMNS或所有列')
    parser.add_argument('--resume', action='store_true', default=DEFAULT_RESUME_ENABLED,
                       help='启用续传功能（如果输出文件已存在，跳过已处理的记录），默认启用')
    parser.add_argument('--no-resume', dest='resume', action='store_false',
                       help='禁用续传功能（强制重新生成所有数据）')
    
    args = parser.parse_args()
    
    # 设置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # 确定输入目录路径
    if args.profile_dir:
        profile_dir = Path(args.profile_dir)
    else:
        logging.error("未指定profile_dir，请在代码中设置DEFAULT_PROFILE_DIR或通过命令行参数提供")
        return
    
    if not profile_dir.exists() or not profile_dir.is_dir():
        logging.error(f"目录不存在: {profile_dir}")
        return
    
    # 确定输出文件路径
    if args.output:
        output_csv = Path(args.output)
    elif DEFAULT_OUTPUT_FILE:
        output_csv = Path(DEFAULT_OUTPUT_FILE)
    else:
        # 默认输出到profile_dir的同级目录，文件名为profile目录名.xlsx
        output_csv = profile_dir.parent / f"{profile_dir.name}.xlsx"
    
    # 确定输出格式
    output_format = args.format
    if output_format is None:
        # 根据文件扩展名判断
        output_format = get_output_format(output_csv)
        # 如果扩展名无法判断，使用默认格式
        if output_format == 'csv' and DEFAULT_OUTPUT_FORMAT:
            output_format = DEFAULT_OUTPUT_FORMAT
            # 修改文件扩展名
            if output_format == 'xlsx':
                output_csv = output_csv.with_suffix('.xlsx')
            elif output_format == 'tsv':
                output_csv = output_csv.with_suffix('.tsv')
    
    # 检查Excel格式的依赖
    if output_format == 'xlsx' and not PANDAS_AVAILABLE:
        logging.error("Excel格式需要pandas和openpyxl库")
        logging.info("请安装: pip install pandas openpyxl")
        logging.info("或者使用CSV格式: --format csv")
        return
    
    logging.info(f"输出格式: {output_format.upper()}")
    if output_format == 'xlsx':
        logging.info("提示: Excel格式是最安全的，完美支持换行符和特殊字符")
    elif output_format == 'csv':
        logging.info("提示: CSV格式已修复换行符处理，但如果问题仍然存在，建议使用Excel格式")
    
    # 执行汇总
    aggregate_results_to_csv(
        profile_dir, 
        output_csv, 
        file_pattern=args.pattern,
        include_columns=args.columns,
        resume=args.resume,
        output_format=output_format
    )
    
    logging.info("汇总完成")


if __name__ == '__main__':
    main()
