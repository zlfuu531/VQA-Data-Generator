"""
评测结果汇总和统计脚本（融合版）
将指定profile文件夹下的所有评测结果文件汇总到一个文件中，并统计各字段正确率
支持JSON和JSONL格式，自动过滤image_path为空的行
"""
import json
import csv
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Set
import argparse
from collections import defaultdict

# 尝试导入pandas（用于Excel格式）
try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    logging.warning("pandas未安装，Excel格式将不可用。可以使用: pip install pandas openpyxl")

# ==================== 可配置的列名列表 ====================
SELECTED_COLUMNS = [
    "question_id", "round", "question", "answer", "question_type",
    "image_type", "image_path", "original_image_path", "profile",
    "scenario", "difficulty", "language", "fintype"
    # 注意：所有模型得分列会自动添加到列表末尾，无需手动指定模型名称
]

# ==================== 默认配置参数 ====================
# 默认输入目录路径（profile目录）
DEFAULT_PROFILE_DIR: Optional[str] = "/home/zenglingfeng/qa_pipline12-7/evaluate/outputs/expert"

# 默认输出文件路径
DEFAULT_OUTPUT_FILE: Optional[str] = "/home/zenglingfeng/qa_pipline12-7/evaluate/benchmark/finmmr/finmmr-1-8.xlsx"

# 默认统计结果输出文件路径
DEFAULT_STATS_OUTPUT_FILE: Optional[str] = "/home/zenglingfeng/qa_pipline12-7/evaluate/benchmark/finmmr/finmmr统计结果1-8.xlsx"

# 默认输出格式
DEFAULT_OUTPUT_FORMAT: str = "xlsx"

# 默认文件匹配模式（None表示匹配所有*.json和*.jsonl文件）
DEFAULT_FILE_PATTERN: Optional[str] = None  # 修改为None，匹配所有json和jsonl文件

# 是否启用续传功能
DEFAULT_RESUME_ENABLED: bool = True

# 基础字段列（非模型列）- 用于统计功能
BASE_COLUMNS = {
    "question_id", "round", "question", "answer", "question_type",
    "image_type", "image_path", "original_image_path", "profile",
    "scenario", "capability", "difficulty", "source", "language",
    "option_A", "option_B", "option_C", "option_D", "fintype"
}


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


def is_image_path_empty(item: Dict[str, Any]) -> bool:
    """
    判断item的image_path是否为空
    
    Args:
        item: 数据项
        
    Returns:
        True表示image_path为空，False表示不为空
    """
    image_path = item.get("image_path")
    
    # None或空字符串视为空
    if image_path is None or image_path == "":
        return True
    
    # 列表类型：空列表或所有元素都为空
    if isinstance(image_path, list):
        if len(image_path) == 0:
            return True
        # 检查列表中的所有元素是否都为空
        if all(not v or (isinstance(v, str) and v.strip() == "") for v in image_path):
            return True
    
    # 字符串类型：只包含空白字符视为空
    if isinstance(image_path, str):
        if image_path.strip() == "":
            return True
    
    return False


def collect_results_from_profile_dir(profile_dir: Path, file_pattern: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    从profile目录下收集所有评测结果文件（支持json和jsonl）
    
    Args:
        profile_dir: profile目录路径（如 outputs/expert）
        file_pattern: 文件匹配模式（如 "eval*.json"），如果为None则匹配所有*.json和*.jsonl文件
        
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
        
        # 查找匹配的文件（支持json和jsonl）
        if file_pattern:
            # 根据文件模式的扩展名决定只匹配哪种类型的文件
            if file_pattern.endswith(".jsonl"):
                json_files = []
                jsonl_files = list(model_dir.glob(file_pattern))
            elif file_pattern.endswith(".json"):
                json_files = list(model_dir.glob(file_pattern))
                jsonl_files = []
            else:
                # 如果模式没有明确的扩展名，尝试匹配两种类型
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


def filter_empty_image_path(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    过滤掉image_path为空的结果
    
    Args:
        results: 结果列表
        
    Returns:
        过滤后的结果列表
    """
    original_count = len(results)
    filtered_results = [item for item in results if not is_image_path_empty(item)]
    filtered_count = len(filtered_results)
    removed_count = original_count - filtered_count
    
    logging.info(f"过滤image_path为空的行: 原始={original_count}, 过滤后={filtered_count}, 移除={removed_count}")
    
    return filtered_results


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
            # 处理image_path：如果是列表，转换为用分号分隔的字符串
            if field == "image_path" and isinstance(value, list):
                base_fields[field] = "; ".join(str(v) for v in value if v)
            else:
                base_fields[field] = value
        else:
            base_fields[field] = None
    
    # 分类字段（可能不存在）
    category_fields = ["scenario", "capability", "difficulty", "source", "language", "original_image_path", "fintype"]
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
            return None
    # 单轮题目：match_gt是布尔值
    elif isinstance(match_gt, bool):
        if round_key:
            return None
        return 1 if match_gt else 0
    else:
        return None


def expand_multi_round_item(item: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    展开多轮题目为多行数据（每轮一行）
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
        
        # 添加round字段
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
                match_gt_value = get_match_gt_value(model_data, round_key)
                if match_gt_value is not None:
                    model_data_copy = model_data.copy()
                    model_data_copy["match_gt"] = bool(match_gt_value)
                    new_item[key] = model_data_copy
                else:
                    model_data_copy = model_data.copy()
                    model_data_copy["match_gt"] = False
                    new_item[key] = model_data_copy
        
        expanded_items.append(new_item)
    
    return expanded_items


def load_existing_csv_records(output_csv: Path, file_format: str = 'csv') -> Dict[str, Dict[str, Any]]:
    """
    加载已存在的文件中的记录（支持CSV/TSV/Excel）
    """
    existing_records = {}
    
    if not output_csv.exists():
        return existing_records
    
    try:
        if file_format == 'xlsx' and PANDAS_AVAILABLE:
            df = pd.read_excel(output_csv, engine='openpyxl')
            for _, row in df.iterrows():
                question_id = str(row.get("question_id", ""))
                round_value = row.get("round")
                round_str = str(round_value) if pd.notna(round_value) and round_value != "" else ""
                key = f"{question_id}|||{round_str}"
                existing_records[key] = row.to_dict()
        else:
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
    """
    question_id = item.get("question_id", "")
    round_value = item.get("round")
    round_str = str(round_value) if round_value is not None else ""
    return f"{question_id}|||{round_str}"


def get_processed_models(existing_row: Dict[str, Any], model_columns: List[str]) -> Set[str]:
    """
    从已存在的行中提取已处理的模型列表
    """
    processed_models = set()
    for model_name in model_columns:
        if model_name in existing_row:
            value = existing_row[model_name]
            if value and str(value).strip():
                processed_models.add(model_name)
    return processed_models


def get_output_format(output_path: Path) -> str:
    """
    根据输出文件扩展名确定输出格式
    """
    ext = output_path.suffix.lower()
    if ext == '.xlsx' or ext == '.xls':
        return 'xlsx'
    elif ext == '.tsv':
        return 'tsv'
    else:
        return 'csv'


def clean_illegal_chars(value: Any) -> Any:
    """
    清理openpyxl不允许的非法字符
    """
    if not isinstance(value, str):
        return value
    
    cleaned = []
    for char in value:
        code = ord(char)
        if code >= 32 or code in (9, 10, 13):
            cleaned.append(char)
    
    return ''.join(cleaned)


def write_to_csv_tsv(all_rows: List[Dict[str, Any]], csv_columns: List[str], 
                     output_path: Path, format_type: str = 'csv'):
    """
    写入CSV或TSV文件
    """
    delimiter = ',' if format_type == 'csv' else '\t'
    
    with open(output_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=csv_columns, delimiter=delimiter, 
                               quoting=csv.QUOTE_MINIMAL, escapechar=None)
        writer.writeheader()
        writer.writerows(all_rows)
    
    logging.info(f"成功写入 {len(all_rows)} 行数据到 {output_path} (格式: {format_type.upper()})")


def write_to_excel(all_rows: List[Dict[str, Any]], csv_columns: List[str], 
                   output_path: Path):
    """
    写入Excel文件
    """
    if not PANDAS_AVAILABLE:
        raise ImportError("pandas未安装，无法使用Excel格式。请安装: pip install pandas openpyxl")
    
    # 清理所有字符串值中的非法字符
    cleaned_rows = []
    for row in all_rows:
        cleaned_row = {}
        for key, value in row.items():
            if isinstance(value, str):
                cleaned_row[key] = clean_illegal_chars(value)
            else:
                cleaned_row[key] = value
        cleaned_rows.append(cleaned_row)
    
    df = pd.DataFrame(cleaned_rows, columns=csv_columns)
    df.to_excel(output_path, index=False, engine='openpyxl', na_rep='')
    
    logging.info(f"成功写入 {len(df)} 行数据到 {output_path} (格式: Excel)")


def aggregate_results_to_csv(
    profile_dir: Path, 
    output_csv: Path, 
    file_pattern: Optional[str] = None,
    include_columns: Optional[List[str]] = None,
    default_columns: Optional[List[str]] = None,
    resume: bool = True,
    output_format: Optional[str] = None,
    filter_empty_image: bool = True
):
    """
    汇总评测结果到文件（支持CSV/TSV/Excel格式）
    """
    logging.info(f"开始汇总 {profile_dir} 下的评测结果")
    
    # 确定输出格式
    if output_format is None:
        output_format = get_output_format(output_csv)
    
    # 如果启用续传功能且输出文件已存在，加载已处理的记录
    existing_records = {}
    if resume and output_csv.exists() and output_format != 'xlsx':
        existing_records = load_existing_csv_records(output_csv, output_format)
        if existing_records:
            logging.info(f"续传模式：发现 {len(existing_records)} 条已处理的记录，将跳过这些记录")
    
    # 收集所有结果
    all_results = collect_results_from_profile_dir(profile_dir, file_pattern=file_pattern)
    
    if not all_results:
        logging.warning(f"在 {profile_dir} 下没有找到任何评测结果文件")
        return
    
    logging.info(f"共收集到 {len(all_results)} 条结果")
    
    # 过滤image_path为空的行
    if filter_empty_image:
        all_results = filter_empty_image_path(all_results)
    
    # 展开多轮题目
    expanded_results = []
    for item in all_results:
        expanded = expand_multi_round_item(item)
        expanded_results.extend(expanded)
    
    logging.info(f"展开多轮题目后共 {len(expanded_results)} 行数据")
    
    # 获取所有模型名称
    model_names = sorted(get_model_names_from_results(expanded_results))
    logging.info(f"找到模型: {model_names}")
    
    # 确定CSV列的顺序
    base_columns = [
        "question_id", "round", "question", "answer", "question_type",
        "image_type", "image_path", "original_image_path", 
        "option_A", "option_B", "option_C", "option_D",
        "profile", "scenario", "capability", "difficulty", "source", "language", "fintype"
    ]
    model_columns = model_names
    
    # 如果启用续传且已有记录，需要从已有记录中提取已存在的模型列
    if resume and existing_records:
        all_existing_models = set()
        for existing_row in existing_records.values():
            for col_name in existing_row.keys():
                if col_name not in base_columns and col_name:
                    all_existing_models.add(col_name)
        model_columns = sorted(set(model_names) | all_existing_models)
        if all_existing_models:
            logging.info(f"续传模式：发现已存在的模型列: {sorted(all_existing_models)}")
    
    all_columns = base_columns + model_columns
    
    # 按record_key分组，合并同一问题的所有模型结果
    items_by_key: Dict[str, List[Dict[str, Any]]] = {}
    for item in expanded_results:
        record_key = get_record_key(item)
        if record_key not in items_by_key:
            items_by_key[record_key] = []
        items_by_key[record_key].append(item)
    
    # 构建CSV行数据（每个record_key只生成一行）
    csv_rows = []
    skipped_models_count = 0
    new_rows_count = 0
    updated_rows_count = 0
    
    for record_key, items in items_by_key.items():
        # 检查是否已存在该记录
        existing_row = None
        processed_models = set()
        if resume and existing_records and record_key in existing_records:
            existing_row = existing_records[record_key]
            processed_models = get_processed_models(existing_row, model_columns)
        
        # 合并所有items中的模型数据
        all_item_models = {}
        first_item = items[0]
        processed_model_names = set()
        
        for item in items:
            model_data = None
            model_name = None
            for key in item.keys():
                if key.startswith("model") and isinstance(item[key], dict):
                    model_data = item[key]
                    model_name = model_data.get("model_name")
                    break
            
            if not model_data or not model_name:
                continue
            
            processed_model_names.add(model_name)
            
            # 检查该模型的answer是否为空
            model_answer = model_data.get("answer", "")
            is_model_answer_empty = (
                model_answer is None or 
                model_answer == "" or 
                (isinstance(model_answer, list) and len(model_answer) == 0) or
                (isinstance(model_answer, dict) and len(model_answer) == 0)
            )
            
            if is_model_answer_empty:
                continue
            
            match_gt = model_data.get("match_gt", False)
            score = 1 if match_gt else 0
            if model_name not in all_item_models:
                all_item_models[model_name] = score
            else:
                all_item_models[model_name] = max(all_item_models[model_name], score)
        
        # 检查需要更新的模型
        models_to_update = set()
        if existing_row:
            for model_name in processed_model_names:
                if model_name not in processed_models:
                    models_to_update.add(model_name)
                elif model_name in all_item_models:
                    new_value = all_item_models[model_name]
                    old_value = existing_row.get(model_name)
                    old_value_int = 0
                    if old_value is not None and str(old_value).strip():
                        try:
                            old_value_int = int(str(old_value).strip())
                        except (ValueError, AttributeError):
                            old_value_int = 0
                    
                    if new_value != old_value_int:
                        models_to_update.add(model_name)
                else:
                    old_value = existing_row.get(model_name)
                    if old_value is not None and str(old_value).strip():
                        models_to_update.add(model_name)
        else:
            models_to_update = processed_model_names
        
        # 如果所有模型都已处理过且数据相同，跳过这个记录
        if resume and existing_row and not models_to_update:
            skipped_models_count += len(processed_model_names)
            continue
        
        # 构建或更新行数据
        if existing_row:
            row = existing_row.copy()
            for model_name in models_to_update:
                if model_name in all_item_models:
                    row[model_name] = all_item_models[model_name]
                else:
                    row[model_name] = ""
            for model_name in model_columns:
                if model_name not in row:
                    row[model_name] = ""
            if models_to_update:
                updated_rows_count += 1
        else:
            row = {}
            
            base_fields = extract_base_fields(first_item)
            row.update(base_fields)
            
            row["round"] = first_item.get("round")
            
            options_cols = extract_options_columns(first_item)
            row.update(options_cols)
            
            for model_name in model_columns:
                if model_name in all_item_models:
                    row[model_name] = all_item_models[model_name]
                else:
                    row[model_name] = ""
            
            new_rows_count += 1
        
        csv_rows.append(row)
    
    if skipped_models_count > 0:
        logging.info(f"续传模式：跳过了 {skipped_models_count} 个已处理的模型结果")
    if updated_rows_count > 0:
        logging.info(f"续传模式：更新了 {updated_rows_count} 行（添加了新模型列）")
    if new_rows_count > 0:
        logging.info(f"续传模式：新增了 {new_rows_count} 行")
    
    # 确定最终要使用的列
    columns_to_use = include_columns or default_columns or SELECTED_COLUMNS
    
    if columns_to_use:
        valid_columns = []
        specified_model_names = set()
        
        for col in columns_to_use:
            if col in all_columns:
                valid_columns.append(col)
            elif col in model_names:
                specified_model_names.add(col)
            else:
                logging.warning(f"列名 '{col}' 不在可用列中，将被忽略")
        
        if not include_columns:
            for model_name in model_columns:
                if model_name not in specified_model_names:
                    valid_columns.append(model_name)
        else:
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
        csv_columns = all_columns
        logging.info(f"使用所有列（共{len(csv_columns)}列）")
    
    # 验证格式
    if output_format == 'xlsx' and not PANDAS_AVAILABLE:
        logging.error("Excel格式需要pandas和openpyxl，请安装: pip install pandas openpyxl")
        logging.info("将改用CSV格式")
        output_format = 'csv'
        output_csv = output_csv.with_suffix('.csv')
    
    # 创建输出目录
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    
    # 如果启用续传且已有记录，需要合并新旧数据
    if resume and existing_records and output_format != 'xlsx':
        csv_rows_by_key = {}
        for row in csv_rows:
            question_id = row.get("question_id", "")
            round_value = row.get("round")
            round_str = str(round_value) if round_value is not None and round_value != "" else ""
            record_key = f"{question_id}|||{round_str}"
            csv_rows_by_key[record_key] = row
        
        all_rows = []
        processed_keys = set()
        
        for existing_key, existing_row in existing_records.items():
            if existing_key in csv_rows_by_key:
                all_rows.append(csv_rows_by_key[existing_key])
            else:
                all_rows.append(existing_row)
            processed_keys.add(existing_key)
        
        for row in csv_rows:
            record_key = get_record_key(row)
            if record_key not in processed_keys:
                all_rows.append(row)
        
        if output_format == 'xlsx':
            write_to_excel(all_rows, csv_columns, output_csv)
        else:
            write_to_csv_tsv(all_rows, csv_columns, output_csv, output_format)
    else:
        if output_format == 'xlsx':
            write_to_excel(csv_rows, csv_columns, output_csv)
        else:
            write_to_csv_tsv(csv_rows, csv_columns, output_csv, output_format)


def get_model_columns(df: pd.DataFrame) -> list:
    """
    从DataFrame中自动识别模型列（排除基础字段列）
    """
    all_columns = set(df.columns)
    model_columns = sorted(all_columns - BASE_COLUMNS)
    return model_columns


def convert_to_score(value) -> int:
    """
    将值转换为得分（0或1）
    """
    if pd.isna(value):
        return None
    
    try:
        if isinstance(value, str):
            value = value.strip()
            if value in ["1", "True", "true", "TRUE"]:
                return 1
            elif value in ["0", "False", "false", "FALSE"]:
                return 0
            else:
                return int(float(value))
        elif isinstance(value, (int, float)):
            return int(value)
        else:
            return None
    except (ValueError, TypeError):
        return None


def analyze_scenario_difficulty_accuracy(excel_path: str, output_path: str = None):
    """
    分析Excel文件中每个模型在不同scenario和difficulty下的正确率
    """
    logging.info(f"正在读取文件进行统计: {excel_path}")
    df = pd.read_excel(excel_path, engine='openpyxl')
    
    logging.info(f"文件总列数: {len(df.columns)}")
    logging.info(f"文件总行数: {len(df)}")
    
    # 检查必要的列
    if "scenario" not in df.columns:
        logging.error("文件中未找到 'scenario' 列")
        logging.info(f"可用的列: {list(df.columns)}")
        return
    
    if "difficulty" not in df.columns:
        logging.error("文件中未找到 'difficulty' 列")
        logging.info(f"可用的列: {list(df.columns)}")
        return
    
    # 自动识别模型列
    model_columns = get_model_columns(df)
    if not model_columns:
        logging.error("未找到任何模型列")
        logging.info(f"基础字段列: {BASE_COLUMNS}")
        logging.info(f"文件中的所有列: {list(df.columns)}")
        return
    
    logging.info(f"找到 {len(model_columns)} 个模型列: {model_columns}")
    
    # 获取scenario和difficulty的唯一值
    scenarios = df["scenario"].dropna().unique()
    difficulties = df["difficulty"].dropna().unique()
    
    # 标准化difficulty值
    difficulty_mapping = {}
    for diff in difficulties:
        diff_str = str(diff).strip().lower()
        difficulty_mapping[diff_str] = diff
    
    # 定义difficulty的标准顺序
    difficulty_order = ["easy", "medium", "hard", "simple", "normal", "complex"]
    sorted_difficulties = []
    for std_diff in difficulty_order:
        for diff_key, diff_value in difficulty_mapping.items():
            if std_diff in diff_key or diff_key in std_diff:
                sorted_difficulties.append(diff_value)
                break
    
    for diff in difficulties:
        if diff not in sorted_difficulties:
            sorted_difficulties.append(diff)
    
    logging.info(f"找到的scenario值: {sorted(scenarios)}")
    logging.info(f"找到的difficulty值: {sorted_difficulties}")
    
    # 统计结果字典
    stats = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: {"total": 0, "correct": 0})))
    
    # 遍历每一行数据
    for idx, row in df.iterrows():
        scenario = row.get("scenario")
        difficulty = row.get("difficulty")
        
        if pd.isna(scenario) or scenario == "":
            continue
        if pd.isna(difficulty) or difficulty == "":
            continue
        
        scenario = str(scenario).strip()
        difficulty = str(difficulty).strip()
        
        for model in model_columns:
            value = row.get(model)
            score = convert_to_score(value)
            
            if score is None:
                continue
            
            stats[model][scenario][difficulty]["total"] += 1
            if score == 1:
                stats[model][scenario][difficulty]["correct"] += 1
    
    # 构建结果表格
    result_rows = []
    
    for model in model_columns:
        row_data = {"模型": model}
        
        for scenario in sorted(scenarios):
            scenario_str = str(scenario).strip()
            for difficulty in sorted_difficulties:
                difficulty_str = str(difficulty).strip()
                
                total = stats[model].get(scenario_str, {}).get(difficulty_str, {}).get("total", 0)
                correct = stats[model].get(scenario_str, {}).get(difficulty_str, {}).get("correct", 0)
                accuracy = (correct / total * 100) if total > 0 else 0.0
                
                col_prefix = f"{scenario_str}_{difficulty_str}"
                row_data[f"{col_prefix}_正确率"] = f"{accuracy:.2f}%"
                row_data[f"{col_prefix}_正确数"] = correct
                row_data[f"{col_prefix}_总数"] = total
        
        # 统计总体
        for difficulty in sorted_difficulties:
            difficulty_str = str(difficulty).strip()
            total_all = 0
            correct_all = 0
            
            for scenario in scenarios:
                scenario_str = str(scenario).strip()
                total_all += stats[model].get(scenario_str, {}).get(difficulty_str, {}).get("total", 0)
                correct_all += stats[model].get(scenario_str, {}).get(difficulty_str, {}).get("correct", 0)
            
            accuracy_all = (correct_all / total_all * 100) if total_all > 0 else 0.0
            
            col_prefix = f"total_{difficulty_str}"
            row_data[f"{col_prefix}_正确率"] = f"{accuracy_all:.2f}%"
            row_data[f"{col_prefix}_正确数"] = correct_all
            row_data[f"{col_prefix}_总数"] = total_all
        
        result_rows.append(row_data)
    
    # 创建结果DataFrame
    result_df = pd.DataFrame(result_rows)
    
    # 确定输出文件路径
    if output_path is None:
        input_path = Path(excel_path)
        output_path = input_path.parent / f"{input_path.stem}_统计结果.xlsx"
    
    # 保存结果
    logging.info(f"正在保存统计结果到: {output_path}")
    result_df.to_excel(output_path, index=False, engine='openpyxl')
    logging.info(f"统计结果已保存，共 {len(result_df)} 个模型")
    
    # 打印结果摘要
    print("\n" + "="*150)
    print("统计结果摘要（按scenario分组）")
    print("="*150)
    
    for scenario in sorted(scenarios):
        scenario_str = str(scenario).strip()
        print(f"\n【{scenario_str}】")
        print("-" * 150)
        
        header_parts = [f"{'模型':<40s}"]
        for difficulty in sorted_difficulties:
            difficulty_str = str(difficulty).strip()
            header_parts.append(f"{scenario_str}_{difficulty_str}")
        header = " | ".join(header_parts)
        print(header)
        print("-" * 150)
        
        for _, row in result_df.iterrows():
            model = row["模型"]
            row_parts = [f"{model:<40s}"]
            for difficulty in sorted_difficulties:
                difficulty_str = str(difficulty).strip()
                col_prefix = f"{scenario_str}_{difficulty_str}"
                accuracy = row.get(f"{col_prefix}_正确率", "0.00%")
                correct = row.get(f"{col_prefix}_正确数", 0)
                total = row.get(f"{col_prefix}_总数", 0)
                cell_value = f"{accuracy} ({correct}/{total})"
                row_parts.append(f"{cell_value:<20s}")
            print(" | ".join(row_parts))
    
    print("\n" + "="*150)
    print("总体统计（所有scenario合并）")
    print("="*150)
    
    header_parts = [f"{'模型':<40s}"]
    for difficulty in sorted_difficulties:
        difficulty_str = str(difficulty).strip()
        header_parts.append(f"total_{difficulty_str}")
    header = " | ".join(header_parts)
    print(header)
    print("-" * 150)
    
    for _, row in result_df.iterrows():
        model = row["模型"]
        row_parts = [f"{model:<40s}"]
        for difficulty in sorted_difficulties:
            difficulty_str = str(difficulty).strip()
            col_prefix = f"total_{difficulty_str}"
            accuracy = row.get(f"{col_prefix}_正确率", "0.00%")
            correct = row.get(f"{col_prefix}_正确数", 0)
            total = row.get(f"{col_prefix}_总数", 0)
            cell_value = f"{accuracy} ({correct}/{total})"
            row_parts.append(f"{cell_value:<20s}")
        print(" | ".join(row_parts))
    
    print("\n" + "="*150)
    logging.info("统计完成")


def main():
    parser = argparse.ArgumentParser(description='汇总评测结果到文件并统计正确率（支持CSV/TSV/Excel格式）')
    parser.add_argument('profile_dir', type=str, nargs='?', default=DEFAULT_PROFILE_DIR,
                       help=f'Profile目录路径（默认：代码中DEFAULT_PROFILE_DIR设置，当前为: {DEFAULT_PROFILE_DIR}）')
    parser.add_argument('--output', type=str, default=None, 
                       help=f'输出文件路径（默认：代码中DEFAULT_OUTPUT_FILE设置，或{{profile_dir}}.xlsx，当前默认: {DEFAULT_OUTPUT_FILE}）')
    parser.add_argument('--stats-output', type=str, default=None,
                       help=f'统计结果输出文件路径（默认：代码中DEFAULT_STATS_OUTPUT_FILE设置，或{{output}}_统计结果.xlsx，当前默认: {DEFAULT_STATS_OUTPUT_FILE}）')
    parser.add_argument('--format', type=str, choices=['csv', 'tsv', 'xlsx'], default=None,
                       help=f'输出格式（csv/tsv/xlsx），如果未指定则根据输出文件扩展名自动判断（默认: {DEFAULT_OUTPUT_FORMAT}）')
    parser.add_argument('--pattern', type=str, default=DEFAULT_FILE_PATTERN, 
                       help=f'文件匹配模式（默认：代码中DEFAULT_FILE_PATTERN设置，或所有*.json和*.jsonl文件）')
    parser.add_argument('--columns', type=str, nargs='+', default=None, 
                       help='要包含的列名列表（例如：--columns question_id round question answer GLM-4.6V），如果不指定则使用代码中的SELECTED_COLUMNS或所有列')
    parser.add_argument('--resume', action='store_true', default=DEFAULT_RESUME_ENABLED,
                       help='启用续传功能（如果输出文件已存在，跳过已处理的记录），默认启用')
    parser.add_argument('--no-resume', dest='resume', action='store_false',
                       help='禁用续传功能（强制重新生成所有数据）')
    parser.add_argument('--no-filter-empty-image', dest='filter_empty_image_path', action='store_false', default=True,
                       help='禁用过滤image_path为空的行（默认启用过滤）')
    parser.add_argument('--no-stats', dest='run_stats', action='store_false', default=True,
                       help='禁用统计功能（默认启用统计）')
    
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
        output_csv = profile_dir.parent / f"{profile_dir.name}.xlsx"
    
    # 确定输出格式
    output_format = args.format
    if output_format is None:
        output_format = get_output_format(output_csv)
        if output_format == 'csv' and DEFAULT_OUTPUT_FORMAT:
            output_format = DEFAULT_OUTPUT_FORMAT
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
    
    # 执行汇总
    aggregate_results_to_csv(
        profile_dir, 
        output_csv, 
        file_pattern=args.pattern,
        include_columns=args.columns,
        resume=args.resume,
        output_format=output_format,
        filter_empty_image=args.filter_empty_image_path
    )
    
    logging.info("汇总完成")
    
    # 执行统计（如果启用）
    if args.run_stats:
        # 确定统计结果输出文件路径
        if args.stats_output:
            stats_output = args.stats_output
        elif DEFAULT_STATS_OUTPUT_FILE:
            stats_output = DEFAULT_STATS_OUTPUT_FILE
        else:
            stats_output = str(output_csv.parent / f"{output_csv.stem}_统计结果.xlsx")
        
        logging.info("开始统计正确率...")
        try:
            analyze_scenario_difficulty_accuracy(str(output_csv), stats_output)
        except Exception as e:
            logging.error(f"统计时出错: {e}", exc_info=True)
    else:
        logging.info("统计功能已禁用")


if __name__ == '__main__':
    main()

