"""
原始数据文件转换为CSV脚本
将指定目录下所有以 _check.json 或 _check.jsonl 结尾的文件转换为CSV格式
"""
import os
import json
import csv
import logging
import io
from pathlib import Path
from typing import Dict, Any, List, Optional
from collections import Counter
import argparse

# ==================== 默认配置参数 ====================
# 默认输入目录路径
DEFAULT_INPUT_DIR: Optional[str] = "/nfsdata-117/project/DeepEyes_Benchmark/QA-Check"
# DEFAULT_INPUT_DIR = None  # 如果设置为None，则必须通过命令行参数提供

# 默认输出文件路径
DEFAULT_OUTPUT_FILE: Optional[str] = "/nfsdata-117/project/DeepEyes_Benchmark/check12-29.csv"
# DEFAULT_OUTPUT_FILE = "/path/to/output.csv"  # 指定默认输出路径

# 默认已存在的CSV文件路径（用于过滤已存在的question_id）
DEFAULT_EXISTING_CSV: Optional[str] = "/nfsdata-117/project/DeepEyes_Benchmark/check12-24.csv"
# DEFAULT_EXISTING_CSV = None  # 如果设置为None，则不进行过滤

# 是否启用续传功能（如果输出文件已存在，跳过已处理的记录）
DEFAULT_RESUME_ENABLED: bool = True

# 默认文件名匹配规则（用于查找要处理的文件）
# 支持两种格式：
# 1. 字符串列表：["*_check.json", "*_check.jsonl"] - 匹配所有以 _check.json 或 _check.jsonl 结尾的文件
# 2. 单个字符串："_check.json" - 只匹配以 _check.json 结尾的文件
DEFAULT_FILE_PATTERNS: List[str] = ["*_check.json", "*_check.jsonl","*_check2.json","*_check2.jsonl"]
# DEFAULT_FILE_PATTERNS = ["*_check.json"]  # 只匹配 _check.json 文件
# DEFAULT_FILE_PATTERNS = ["*_check.jsonl"]  # 只匹配 _check.jsonl 文件

# 字段映射：将原始字段名映射为标准字段名
FIELD_MAPPING = {
    "L_Level": "difficulty",  # L_Level 映射为 difficulty
    "L_level": "difficulty",   # 兼容小写版本
    "l_level": "difficulty",   # 兼容全小写版本
    # 可以添加更多字段映射
}

# ==================== 题型筛选配置 ====================
# 指定要保留的题型列表，只保留列表中指定的题型
# 如果设置为 None 或空列表 []，则保留所有题型（不过滤）
# 示例：ALLOWED_QUESTION_TYPES = ["问答题", "多轮问答题"]  # 只保留问答题和多轮问答题
ALLOWED_QUESTION_TYPES: Optional[List[str]] = ["问答题", "多轮问答题"]
# ALLOWED_QUESTION_TYPES = None  # 设置为None表示保留所有题型

# ==================== 可配置的列名列表 ====================
# 参考 aggregate_results.py 的 SELECTED_COLUMNS
SELECTED_COLUMNS = [
    "question_id", "round", "question", "answer", "question_type",
    "image_type", "image_path", "original_image_path", "profile",
    "difficulty", "language"
    # 注意：没有模型得分列
]
# SELECTED_COLUMNS = None  # 设置为None表示保存所有列


def load_json(file_path: Path) -> Dict[str, Any]:
    """
    加载JSON文件
    
    说明：
        - 正常情况下文件应为单个合法的JSON对象或数组
        - 如果遇到 "Extra data" 之类错误，说明文件里可能是按行写了多个JSON
          （本质上是 JSONL 格式但扩展名仍为 .json），这时自动按JSONL方式逐行解析
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        # 典型报错：Extra data: line 2 column 1 (char xxx)
        if "Extra data" in str(e):
            logging.warning(
                f"文件 {file_path} 解析为单一JSON失败（{e}），疑似多段JSON，将按JSONL逐行解析"
            )
            # 按JSONL解析，返回列表
            return load_jsonl(file_path)
        # 其他JSON错误，继续抛出，由上层统一处理
        raise


def load_jsonl(file_path: Path) -> List[Dict[str, Any]]:
    """加载JSONL文件"""
    results = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
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


def find_check_files(input_dir: Path, file_patterns: Optional[List[str]] = None) -> List[Path]:
    """
    递归查找匹配指定模式的文件
    
    Args:
        input_dir: 输入目录路径
        file_patterns: 文件名匹配模式列表（如 ["*_check.json", "*_check.jsonl"]），如果为None则使用DEFAULT_FILE_PATTERNS
        
    Returns:
        找到的文件路径列表
    """
    if file_patterns is None:
        file_patterns = DEFAULT_FILE_PATTERNS
    
    check_files = []
    
    # 根据每个模式查找文件
    for pattern in file_patterns:
        for file_path in input_dir.rglob(pattern):
            check_files.append(file_path)
    
    # 去重并排序
    return sorted(set(check_files))


def normalize_field_name(field_name: str) -> str:
    """
    标准化字段名（应用字段映射）
    
    Args:
        field_name: 原始字段名
        
    Returns:
        标准化后的字段名
    """
    return FIELD_MAPPING.get(field_name, field_name)


def normalize_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    标准化数据项（应用字段映射和转换）
    
    Args:
        item: 原始数据项
        
    Returns:
        标准化后的数据项
    """
    normalized = {}
    
    # 应用字段映射
    for key, value in item.items():
        normalized_key = normalize_field_name(key)
        normalized[normalized_key] = value
    
    # 确保 question_id 是字符串
    if "question_id" in normalized:
        normalized["question_id"] = str(normalized["question_id"])
    
    # 处理 image_path：如果是字符串，转换为列表格式（与 aggregate_results.py 保持一致）
    if "image_path" in normalized:
        image_path = normalized["image_path"]
        if isinstance(image_path, str) and image_path:
            normalized["image_path"] = [image_path]
        elif not isinstance(image_path, list):
            normalized["image_path"] = []
    
    # 处理 original_image_path（如果存在）
    if "original_image_path" in normalized:
        original_image_path = normalized["original_image_path"]
        if isinstance(original_image_path, str) and original_image_path:
            normalized["original_image_path"] = [original_image_path]
        elif not isinstance(original_image_path, list):
            normalized["original_image_path"] = []
    
    return normalized


def extract_base_fields(item: Dict[str, Any]) -> Dict[str, Any]:
    """提取基础字段和分类字段（参考 aggregate_results.py）"""
    base_fields = {}
    
    # 基础字段
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
    提取options字段，转换为A, B, C, D四列（参考 aggregate_results.py）
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


def expand_multi_round_item(item: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    展开多轮题目为多行数据（每轮一行，参考 aggregate_results.py）
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
        
        expanded_items.append(new_item)
    
    return expanded_items


def get_record_key(item: Dict[str, Any]) -> str:
    """
    获取数据项的唯一标识键（基于question_id和round）
    
    Args:
        item: 数据项（已包含round字段）
        
    Returns:
        唯一标识键字符串
    """
    question_id = item.get("question_id", "")
    round_value = item.get("round")
    # 统一处理：None、空字符串、字符串"None"都转换为空字符串
    if round_value is None or round_value == "" or str(round_value).strip().lower() == "none":
        round_str = ""
    else:
        round_str = str(round_value).strip()
    return f"{question_id}|||{round_str}"


def load_existing_csv_records(output_csv: Path) -> Dict[str, Dict[str, Any]]:
    """
    加载已存在的CSV文件中的记录
    
    Args:
        output_csv: CSV文件路径
        
    Returns:
        字典，key为 (question_id, round) 的元组转换为字符串，value为该行的完整数据
    """
    existing_records = {}
    
    if not output_csv.exists():
        return existing_records
    
    try:
        duplicate_existing_count = 0  # 统计旧CSV内部重复的 (question_id, round)
        with open(output_csv, 'r', encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                question_id = row.get("question_id", "")
                round_value = row.get("round", "")
                # 统一处理：None、空字符串、字符串"None"都转换为空字符串
                if round_value is None or round_value == "" or str(round_value).strip().lower() == "none":
                    round_str = ""
                else:
                    round_str = str(round_value).strip()
                key = f"{question_id}|||{round_str}"
                if key in existing_records:
                    # 旧CSV自身就有重复行，这里保留最新一行，但记录重复情况
                    duplicate_existing_count += 1
                    logging.warning(
                        f"检测到旧CSV中存在重复记录 question_id={question_id}, round={round_str}，"
                        f"该键之前已出现过，将使用文件中后出现的这一行覆盖前一行"
                    )
                existing_records[key] = row
        
        logging.info(f"从现有CSV文件加载了 {len(existing_records)} 条去重后的已处理记录")
        if duplicate_existing_count > 0:
            logging.warning(
                f"旧CSV内部去重：发现 {duplicate_existing_count} 条重复的 (question_id, round) 记录，"
                f"这些重复行已在内存中合并为最新的一条"
            )
    except Exception as e:
        logging.warning(f"读取现有CSV文件失败 {output_csv}: {e}，将重新生成")
        existing_records = {}
    
    return existing_records


def load_existing_question_ids(existing_csv: Path) -> set:
    """
    加载已存在的CSV文件中的所有question_id集合
    
    Args:
        existing_csv: 已存在的CSV文件路径
        
    Returns:
        question_id的集合
    """
    existing_question_ids = set()
    
    if not existing_csv or not existing_csv.exists():
        return existing_question_ids
    
    try:
        with open(existing_csv, 'r', encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                question_id = row.get("question_id", "")
                if question_id:
                    existing_question_ids.add(str(question_id))
        
        logging.info(f"从已存在CSV文件 {existing_csv} 加载了 {len(existing_question_ids)} 个唯一的question_id")
    except Exception as e:
        logging.warning(f"读取已存在CSV文件失败 {existing_csv}: {e}，将不进行过滤")
        existing_question_ids = set()
    
    return existing_question_ids


def count_non_empty_fields(item: Dict[str, Any], important_fields: List[str] = None) -> int:
    """
    计算数据项中非空字段的数量
    
    Args:
        item: 数据项
        important_fields: 重要字段列表（如language、difficulty等），如果提供，会优先计算这些字段
        
    Returns:
        非空字段的数量
    """
    if important_fields is None:
        important_fields = ["language", "difficulty", "scenario", "capability", "source", "profile"]
    
    count = 0
    # 先计算重要字段
    important_count = 0
    for field in important_fields:
        value = item.get(field)
        if value is not None and value != "" and str(value).strip().lower() != "none":
            important_count += 1
    
    # 计算所有字段
    for key, value in item.items():
        # 跳过内部字段
        if key.startswith("_"):
            continue
        if value is not None and value != "" and str(value).strip().lower() != "none":
            count += 1
    
    # 返回重要字段数量 * 100 + 总字段数量，这样重要字段多的会优先
    return important_count * 100 + count


def convert_raw_data_to_csv(
    input_dir: Path,
    output_csv: Path,
    include_columns: Optional[List[str]] = None,
    file_patterns: Optional[List[str]] = None,
    resume: bool = True,
    allowed_question_types: Optional[List[str]] = None,
    existing_csv: Optional[Path] = None
):
    """
    将原始数据文件转换为CSV
    
    Args:
        input_dir: 输入目录路径
        output_csv: 输出CSV文件路径
        include_columns: 要包含的列列表（如果为None则使用SELECTED_COLUMNS或所有列）
        file_patterns: 文件名匹配模式列表（如果为None则使用DEFAULT_FILE_PATTERNS）
        resume: 是否启用续传功能（如果输出文件已存在，跳过已处理的记录）
        allowed_question_types: 允许的题型列表（如果为None或空列表则保留所有题型）
        existing_csv: 已存在的CSV文件路径（用于过滤已存在的question_id）
    """
    logging.info(f"开始转换 {input_dir} 下的原始数据文件")
    
    # 加载已存在的question_id集合（用于过滤新增数据）
    existing_question_ids = set()
    if existing_csv:
        existing_question_ids = load_existing_question_ids(existing_csv)
        if existing_question_ids:
            logging.info(f"过滤模式：将从已存在CSV文件 {existing_csv} 中过滤掉 {len(existing_question_ids)} 个已存在的question_id")
    
    # 如果启用续传功能且输出文件已存在，加载已处理的记录
    existing_records = {}
    if resume and output_csv.exists():
        existing_records = load_existing_csv_records(output_csv)
        if existing_records:
            logging.info(f"续传模式：发现 {len(existing_records)} 条已处理的记录，将跳过这些记录")
    
    # 查找匹配的文件
    if file_patterns is None:
        file_patterns = DEFAULT_FILE_PATTERNS
    check_files = find_check_files(input_dir, file_patterns=file_patterns)
    
    logging.info(f"使用文件匹配模式: {file_patterns}")
    
    if not check_files:
        logging.warning(f"在 {input_dir} 下没有找到匹配模式 {file_patterns} 的文件")
        return
    
    logging.info(f"找到 {len(check_files)} 个文件")
    logging.info("=" * 80)
    logging.info("处理的文件列表：")
    for i, file_path in enumerate(check_files, 1):
        logging.info(f"  {i}. {file_path}")
    logging.info("=" * 80)
    
    # 收集所有数据（记录每个文件处理的数据量）
    all_items = []
    file_stats = {}  # 记录每个文件处理的数据量
    
    for file_path in check_files:
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
                    file_stats[str(file_path)] = {"loaded": 0, "error": "无法解析文件格式"}
                    continue
            
            # 标准化每个item，并记录来源文件
            normalized_items = []
            for item in items:
                normalized_item = normalize_item(item)
                # 记录来源文件（用于后续统计空值来源）
                normalized_item["_source_file"] = str(file_path)
                normalized_items.append(normalized_item)
            
            file_stats[str(file_path)] = {"loaded": len(normalized_items), "error": None}
            logging.info(f"从 {file_path} 加载了 {len(normalized_items)} 条数据")
            all_items.extend(normalized_items)
        except Exception as e:
            logging.error(f"加载文件失败 {file_path}: {e}")
            file_stats[str(file_path)] = {"loaded": 0, "error": str(e)}
            continue
    
    if not all_items:
        logging.warning("没有加载到任何数据")
        return
    
    logging.info(f"共收集到 {len(all_items)} 条数据")
    
    # 展开多轮题目
    expanded_items = []
    for item in all_items:
        expanded = expand_multi_round_item(item)
        expanded_items.extend(expanded)
    
    expanded_count_after_expand = len(expanded_items)
    logging.info(f"展开多轮题目后共 {expanded_count_after_expand} 行数据")
    
    # 题型筛选（优先使用函数参数，否则使用全局配置）
    question_types_to_filter = allowed_question_types if allowed_question_types is not None else ALLOWED_QUESTION_TYPES
    
    filtered_by_type_count = 0
    if question_types_to_filter and len(question_types_to_filter) > 0:
        filtered_items = []
        filtered_count = 0
        filtered_by_file = Counter()  # 记录每个文件被过滤的数量
        for item in expanded_items:
            question_type = item.get("question_type", "")
            source_file = item.get("_source_file", "unknown")
            # 检查 question_type 是否在允许的列表中
            if question_type in question_types_to_filter:
                filtered_items.append(item)
            else:
                filtered_count += 1
                filtered_by_file[source_file] += 1
        
        filtered_by_type_count = filtered_count
        expanded_items = filtered_items
        logging.info(f"题型筛选：保留 {question_types_to_filter}，过滤掉 {filtered_count} 行，剩余 {len(expanded_items)} 行")
        if filtered_count > 0:
            logging.info("题型筛选被过滤的数据来源文件统计：")
            for file_path, count in filtered_by_file.most_common():
                logging.info(f"  - {file_path}: {count} 行")
    else:
        logging.info("题型筛选：未启用（保留所有题型）")
    
    expanded_count_after_type_filter = len(expanded_items)
    
    # ==================== 统计字段分布与题目数量 ====================
    # 1. 统计字段分布（基于展开后的行）
    fields_to_count = ["question_type", "image_type", "profile", "difficulty", "language"]
    field_counters = {field: Counter() for field in fields_to_count}
    
    # 统计所有字段的空值来源文件（按字段名组织）
    empty_value_by_field_and_file = {field: Counter() for field in fields_to_count}  # field -> {file_path: count}
    
    for item in expanded_items:
        source_file = item.get("_source_file", "unknown")
        for field in fields_to_count:
            value = item.get(field)
            # 统一将 None 转成 "None" 方便统计和展示
            key = str(value) if value is not None else "None"
            field_counters[field][key] += 1
            
            # 统计空值来源（None、空字符串、字符串"None"都视为空）
            if value is None or value == "" or str(value).strip().lower() == "none":
                empty_value_by_field_and_file[field][source_file] += 1
    
    # 保留原有的空值统计（用于兼容后续代码）
    empty_difficulty_by_file = empty_value_by_field_and_file.get("difficulty", Counter())
    empty_language_by_file = empty_value_by_field_and_file.get("language", Counter())
    
    # 2. 统计按 question_id 的单轮/多轮题目数量（基于未展开的 all_items）
    question_ids_seen = set()
    total_questions = 0
    single_round_questions = 0
    multi_round_questions = 0
    for item in all_items:
        qid = item.get("question_id")
        if qid in question_ids_seen:
            continue
        question_ids_seen.add(qid)
        total_questions += 1
        q = item.get("question")
        a = item.get("answer")
        if isinstance(q, dict) and isinstance(a, dict):
            multi_round_questions += 1
        else:
            single_round_questions += 1
    
    # 过滤已存在的question_id（只保留新增的）
    new_items = []
    filtered_by_question_id_count = 0
    expanded_count_after_question_id_filter = len(expanded_items)
    filtered_by_question_id_by_file = Counter()  # 记录每个文件被过滤的数量
    if existing_question_ids:
        for item in expanded_items:
            question_id = str(item.get("question_id", ""))
            source_file = item.get("_source_file", "unknown")
            if question_id not in existing_question_ids:
                new_items.append(item)
            else:
                filtered_by_question_id_count += 1
                filtered_by_question_id_by_file[source_file] += 1
        
        expanded_count_after_question_id_filter = len(new_items)
        logging.info(f"过滤已存在的question_id：过滤掉 {filtered_by_question_id_count} 行，剩余 {expanded_count_after_question_id_filter} 行新增数据")
        if filtered_by_question_id_count > 0:
            logging.info("过滤已存在question_id被过滤的数据来源文件统计：")
            for file_path, count in filtered_by_question_id_by_file.most_common():
                logging.info(f"  - {file_path}: {count} 行")
        expanded_items = new_items
    
    # 对于相同的question_id，选择字段最全的那个（按question_id分组，但保留所有round）
    # 首先按question_id分组，找出哪些question_id有重复
    question_id_to_items = {}  # question_id -> [(item, source_file, field_count, round), ...]
    duplicate_question_ids = {}  # question_id -> [(source_file, question, round), ...] 用于日志输出
    
    for item in expanded_items:
        question_id = str(item.get("question_id", ""))
        if not question_id:
            continue
        
        source_file = item.get("_source_file", "unknown")
        question = item.get("question", "")
        round_value = item.get("round")
        field_count = count_non_empty_fields(item)
        
        if question_id not in question_id_to_items:
            question_id_to_items[question_id] = []
        
        question_id_to_items[question_id].append((item, source_file, field_count, round_value))
    
    # 对于每个question_id，找出重复的记录（来自不同文件但question_id相同）
    # 按question_id分组，选择字段最全的那个文件的所有记录
    question_id_to_best_file = {}  # question_id -> best_source_file
    question_id_to_best_field_count = {}  # question_id -> best_field_count
    
    for question_id, items_list in question_id_to_items.items():
        # 检查是否来自不同文件（只有来自不同文件才认为是重复）
        source_files = set()
        for item, source_file, field_count, round_value in items_list:
            source_files.add(source_file)
        
        if len(source_files) > 1:
            # 来自不同文件，需要选择字段最全的那个文件
            file_to_max_count = {}  # source_file -> max_field_count
            for item, source_file, field_count, round_value in items_list:
                if source_file not in file_to_max_count:
                    file_to_max_count[source_file] = 0
                file_to_max_count[source_file] = max(file_to_max_count[source_file], field_count)
            
            # 选择字段最多的文件
            best_file = max(file_to_max_count.items(), key=lambda x: x[1])[0]
            best_count = file_to_max_count[best_file]
            question_id_to_best_file[question_id] = best_file
            question_id_to_best_field_count[question_id] = best_count
            
            # 记录重复信息（用于日志输出）
            duplicate_question_ids[question_id] = []
            for item, source_file, field_count, round_value in items_list:
                item_question = item.get("question", "")
                duplicate_question_ids[question_id].append((source_file, item_question, round_value))
    
    # 选择每个question_id中字段最全的那个文件的所有记录
    selected_items = []
    duplicate_selected_count = 0
    for question_id, items_list in question_id_to_items.items():
        if question_id in question_id_to_best_file:
            # 有重复，只保留字段最全的文件中的记录
            best_file = question_id_to_best_file[question_id]
            for item, source_file, field_count, round_value in items_list:
                if source_file == best_file:
                    selected_items.append(item)
                else:
                    duplicate_selected_count += 1
        else:
            # 没有重复，保留所有记录
            for item, source_file, field_count, round_value in items_list:
                selected_items.append(item)
    
    if duplicate_selected_count > 0:
        logging.info(f"相同question_id去重：发现 {len(duplicate_question_ids)} 个重复的question_id，共 {duplicate_selected_count} 条重复记录，已选择字段最全的文件中的记录")
        logging.info("=" * 80)
        logging.info("重复的question_id详情（路径文件和问题）：")
        for question_id, duplicate_list in duplicate_question_ids.items():
            best_file = question_id_to_best_file.get(question_id, "")
            logging.info(f"  question_id: {question_id} (选择文件: {best_file})")
            for idx, (source_file, question, round_value) in enumerate(duplicate_list, 1):
                # 截断过长的question
                question_str = str(question)
                if len(question_str) > 100:
                    question_str = question_str[:100] + "..."
                round_str = f", round={round_value}" if round_value is not None else ""
                selected_mark = " [已选择]" if source_file == best_file else " [已过滤]"
                logging.info(f"    {idx}. 文件: {source_file}{selected_mark}{round_str}")
                logging.info(f"       问题: {question_str}")
            logging.info("")
        logging.info("=" * 80)
    
    expanded_count_after_dedup = len(selected_items)
    expanded_items = selected_items
    logging.info(f"去重后剩余 {len(expanded_items)} 行数据")
    
    # 构建CSV行数据（续传模式：跳过已存在的记录，同时在本次运行内按 question_id+round 去重）
    csv_rows = []
    skipped_count = 0          # 续传时跳过的行数（已在旧CSV中存在）
    new_count = 0              # 本次真正新增的行数
    duplicate_in_input_count = 0  # 本次输入数据内部的重复行数（同一 question_id+round 出现多次）
    seen_keys = set()          # 本次运行中已出现的 record_key 集合
    
    for item in expanded_items:
        record_key = get_record_key(item)
        
        # 1）续传：如果在旧CSV中已经有这一行，直接跳过
        if resume and existing_records and record_key in existing_records:
            skipped_count += 1
            continue
        
        # 2）本次输入数据内部去重：同一次运行中，同一个 question_id+round 只保留一条
        if record_key in seen_keys:
            duplicate_in_input_count += 1
            continue
        seen_keys.add(record_key)
        
        row = {}
        
        # 提取基础字段
        base_fields = extract_base_fields(item)
        row.update(base_fields)
        
        # 添加round字段（多轮题目显示为数字1,2,3...，单轮题目为None）
        row["round"] = item.get("round")
        
        # 提取options为A/B/C/D列
        options_cols = extract_options_columns(item)
        row.update(options_cols)
        
        csv_rows.append(row)
        new_count += 1
    
    # 统计最终写入CSV的数据
    final_question_ids = set()
    for row in csv_rows:
        question_id = row.get("question_id", "")
        if question_id:
            final_question_ids.add(str(question_id))
    final_question_count = len(final_question_ids)
    
    # 输出详细的统计信息
    logging.info("=" * 80)
    logging.info("数据统计信息：")
    logging.info(f"  总文件数: {len(check_files)}")
    logging.info(f"  总加载数据: {len(all_items)} 条（原始数据，未展开）")
    logging.info(f"  展开后数据: {expanded_count_after_expand} 行（多轮题目展开后）")
    if filtered_by_type_count > 0:
        logging.info(f"  题型筛选后: {expanded_count_after_type_filter} 行（过滤掉 {filtered_by_type_count} 行）")
    if existing_question_ids:
        logging.info(f"  过滤已存在question_id后: {expanded_count_after_question_id_filter} 行（过滤掉 {filtered_by_question_id_count} 行）")
    if duplicate_selected_count > 0:
        logging.info(f"  去重后: {expanded_count_after_dedup} 行（过滤掉 {duplicate_selected_count} 行重复）")
    if resume and existing_records:
        logging.info(f"  续传模式跳过: {skipped_count} 行（已在输出文件中存在）")
    logging.info(f"  最终写入CSV: {new_count} 行，{final_question_count} 个不同question_id")
    logging.info("")
    logging.info(f"  原始题目统计（基于未过滤的原始数据）:")
    logging.info(f"    题目总数（按 question_id 去重）: {total_questions}")
    logging.info(f"      单轮题目数: {single_round_questions}")
    logging.info(f"      多轮题目数: {multi_round_questions}")
    logging.info("")
    logging.info("字段分布统计（基于展开后的行）：")
    for field in fields_to_count:
        counter = field_counters[field]
        logging.info(f"  [{field}] 共 {sum(counter.values())} 条，去重后 {len(counter)} 个取值")
        # 按出现次数从多到少排序
        for value, cnt in counter.most_common():
            logging.info(f"    - {field} = {value!r}: {cnt} 条")
            # 如果是空值（None、空字符串、字符串"None"），显示来源文件路径统计
            is_empty = (value == "None" or value == "" or 
                       (isinstance(value, str) and value.strip().lower() == "none"))
            if is_empty:
                empty_files = empty_value_by_field_and_file.get(field, Counter())
                if empty_files:
                    total_empty_count = sum(empty_files.values())
                    logging.info(f"      空值来源文件路径统计（共 {total_empty_count} 条空值）：")
                    # 按文件路径统计，按数量从多到少排序
                    for file_path, file_count in empty_files.most_common():
                        logging.info(f"        - {file_path}: {file_count} 条")
    
    # 统计空值来源文件
    if empty_difficulty_by_file or empty_language_by_file:
        logging.info("")
        logging.info("空值来源文件统计：")
        if empty_difficulty_by_file:
            total_empty_diff = sum(empty_difficulty_by_file.values())
            logging.info(f"  [difficulty] 共有 {total_empty_diff} 条记录为空值，来自以下文件：")
            # 按空值数量从多到少排序
            for file_path, count in empty_difficulty_by_file.most_common():
                logging.info(f"    - {file_path}: {count} 条")
        else:
            logging.info(f"  [difficulty] 无空值")
        
        if empty_language_by_file:
            total_empty_lang = sum(empty_language_by_file.values())
            logging.info(f"  [language] 共有 {total_empty_lang} 条记录为空值，来自以下文件：")
            # 按空值数量从多到少排序
            for file_path, count in empty_language_by_file.most_common():
                logging.info(f"    - {file_path}: {count} 条")
        else:
            logging.info(f"  [language] 无空值")
    
    if existing_question_ids:
        logging.info(f"  过滤已存在question_id统计:")
        logging.info(f"    - 已存在question_id数量: {len(existing_question_ids)}")
        logging.info(f"    - 过滤掉的数据: {filtered_by_question_id_count} 行")
        logging.info(f"    - 新增数据（去重前）: {len(expanded_items) + filtered_by_question_id_count} 行")
    
    if resume and existing_records:
        logging.info(f"  续传模式统计:")
        logging.info(f"    - 已存在记录: {len(existing_records)} 行")
        logging.info(f"    - 跳过重复数据: {skipped_count} 行")
        logging.info(f"    - 新增数据: {new_count} 行")
        if len(expanded_items) > 0:
            logging.info(f"    - 重复率: {skipped_count / len(expanded_items) * 100:.2f}%")
    else:
        logging.info(f"  新增数据: {new_count} 行")
        if duplicate_in_input_count > 0:
            logging.info(f"  本次输入数据内部去重: 跳过 {duplicate_in_input_count} 条重复的 (question_id, round) 记录")
    logging.info("=" * 80)
    
    if skipped_count > 0:
        logging.info(f"续传模式：跳过了 {skipped_count} 条已处理的记录")
    if new_count == 0 and resume and existing_records:
        logging.warning("所有数据都已处理过，没有新数据需要添加")
        return
    
    # 确定CSV列的顺序
    base_columns = [
        "question_id", "round", "question", "answer", "question_type",
        "image_type", "image_path", "original_image_path", 
        "option_A", "option_B", "option_C", "option_D",
        "profile", "scenario", "capability", "difficulty", "source", "language"
    ]
    all_columns = base_columns
    
    # 确定最终要使用的列
    columns_to_use = include_columns or SELECTED_COLUMNS
    
    if columns_to_use:
        # 使用指定的列
        valid_columns = []
        for col in columns_to_use:
            if col in all_columns:
                valid_columns.append(col)
            else:
                logging.warning(f"列名 '{col}' 不在可用列中，将被忽略")
        
        if not valid_columns:
            logging.warning("指定的列中没有有效列，将使用所有列")
            csv_columns = all_columns
        else:
            csv_columns = valid_columns
            source = "命令行参数" if include_columns else "代码中的SELECTED_COLUMNS"
            logging.info(f"使用{source}指定的列: {csv_columns}")
    else:
        # 使用所有列
        csv_columns = all_columns
        logging.info(f"使用所有列（共{len(csv_columns)}列）")
    
    # 写入CSV文件
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    
    # 如果启用续传且已有记录，需要合并新旧数据
    if resume and existing_records:
        # 创建一个映射，将csv_rows按record_key索引
        csv_rows_by_key = {}
        for row in csv_rows:
            record_key = get_record_key(row)
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
        
        # 写入所有行（对image_path、original_image_path、question、answer字段特殊处理，确保用引号包裹）
        with open(output_csv, 'w', encoding='utf-8', newline='') as f:
            # 需要强制引号的字段
            force_quote_fields = {"image_path", "original_image_path", "question", "answer"}
            
            # 写入表头
            writer = csv.DictWriter(f, fieldnames=csv_columns, quoting=csv.QUOTE_MINIMAL)
            writer.writeheader()
            
            # 手动格式化并写入数据行
            for row in all_rows:
                # 先使用csv模块处理所有字段（自动处理包含逗号的字段）
                temp_buffer = io.StringIO()
                temp_writer = csv.writer(temp_buffer, quoting=csv.QUOTE_MINIMAL)
                
                row_values = []
                for col in csv_columns:
                    value = str(row.get(col, ""))
                    if col in force_quote_fields and value:
                        # 对这两个字段，使用QUOTE_ALL确保总是加引号
                        temp_field_buffer = io.StringIO()
                        temp_field_writer = csv.writer(temp_field_buffer, quoting=csv.QUOTE_ALL)
                        temp_field_writer.writerow([value])
                        quoted_value = temp_field_buffer.getvalue().strip()
                        row_values.append(quoted_value)
                    else:
                        # 其他字段，使用csv模块自动处理
                        temp_field_buffer = io.StringIO()
                        temp_field_writer = csv.writer(temp_field_buffer, quoting=csv.QUOTE_MINIMAL)
                        temp_field_writer.writerow([value])
                        formatted_value = temp_field_buffer.getvalue().strip()
                        row_values.append(formatted_value)
                
                # 手动写入CSV行（所有字段都已正确格式化）
                f.write(','.join(row_values) + '\n')
        
        logging.info(f"成功合并并写入 {len(all_rows)} 行数据到 {output_csv}（其中 {len(existing_records)} 条原有记录，{new_count} 条新增记录）")
    else:
        # 直接写入所有记录（新文件或禁用续传，对image_path、original_image_path、question、answer字段特殊处理）
        with open(output_csv, 'w', encoding='utf-8', newline='') as f:
            # 需要强制引号的字段
            force_quote_fields = {"image_path", "original_image_path", "question", "answer"}
            
            # 写入表头
            writer = csv.DictWriter(f, fieldnames=csv_columns, quoting=csv.QUOTE_MINIMAL)
            writer.writeheader()
            
            # 手动格式化并写入数据行
            for row in csv_rows:
                # 先使用csv模块处理所有字段（自动处理包含逗号的字段）
                row_values = []
                for col in csv_columns:
                    value = str(row.get(col, ""))
                    if col in force_quote_fields and value:
                        # 对这两个字段，使用QUOTE_ALL确保总是加引号
                        temp_field_buffer = io.StringIO()
                        temp_field_writer = csv.writer(temp_field_buffer, quoting=csv.QUOTE_ALL)
                        temp_field_writer.writerow([value])
                        quoted_value = temp_field_buffer.getvalue().strip()
                        row_values.append(quoted_value)
                    else:
                        # 其他字段，使用csv模块自动处理
                        temp_field_buffer = io.StringIO()
                        temp_field_writer = csv.writer(temp_field_buffer, quoting=csv.QUOTE_MINIMAL)
                        temp_field_writer.writerow([value])
                        formatted_value = temp_field_buffer.getvalue().strip()
                        row_values.append(formatted_value)
                
                # 手动写入CSV行（所有字段都已正确格式化）
                f.write(','.join(row_values) + '\n')
        
        logging.info(f"成功写入 {len(csv_rows)} 行数据到 {output_csv}")


def main():
    parser = argparse.ArgumentParser(description='将原始数据文件转换为CSV')
    parser.add_argument('--input', type=str, default=DEFAULT_INPUT_DIR,
                       help=f'输入目录路径（默认：代码中DEFAULT_INPUT_DIR设置，当前为: {DEFAULT_INPUT_DIR}）')
    parser.add_argument('--output', type=str, default=DEFAULT_OUTPUT_FILE,
                       help=f'输出CSV文件路径（默认：代码中DEFAULT_OUTPUT_FILE设置，或 input_dir/raw_data.csv）')
    parser.add_argument('--patterns', type=str, nargs='+', default=None,
                       help=f'文件名匹配模式列表（例如：--patterns "*_check.json" "*_check.jsonl"），如果不指定则使用代码中的DEFAULT_FILE_PATTERNS（当前为: {DEFAULT_FILE_PATTERNS}）')
    parser.add_argument('--columns', type=str, nargs='+', default=None,
                       help='要包含的列名列表（例如：--columns question_id round question answer），如果不指定则使用代码中的SELECTED_COLUMNS或所有列')
    parser.add_argument('--question-types', type=str, nargs='+', default=None,
                       help=f'允许的题型列表（例如：--question-types "问答题" "多轮问答题"），如果不指定则使用代码中的ALLOWED_QUESTION_TYPES（当前为: {ALLOWED_QUESTION_TYPES}），设置为空则保留所有题型')
    parser.add_argument('--resume', action='store_true', default=DEFAULT_RESUME_ENABLED,
                       help='启用续传功能（如果输出文件已存在，跳过已处理的记录），默认启用')
    parser.add_argument('--no-resume', dest='resume', action='store_false',
                       help='禁用续传功能（强制重新生成所有数据）')
    parser.add_argument('--existing-csv', type=str, default=DEFAULT_EXISTING_CSV,
                       help=f'已存在的CSV文件路径（用于过滤已存在的question_id，默认：代码中DEFAULT_EXISTING_CSV设置，当前为: {DEFAULT_EXISTING_CSV}）')
    
    args = parser.parse_args()
    
    # 设置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # 确定输入目录路径
    if args.input:
        input_dir = Path(args.input)
    else:
        logging.error("未指定input_dir，请在代码中设置DEFAULT_INPUT_DIR或通过命令行参数提供")
        return
    
    if not input_dir.exists() or not input_dir.is_dir():
        logging.error(f"目录不存在: {input_dir}")
        return
    
    # 确定输出文件路径
    if args.output:
        output_csv = Path(args.output)
    elif DEFAULT_OUTPUT_FILE:
        output_csv = Path(DEFAULT_OUTPUT_FILE)
    else:
        # 默认输出到input_dir的同级目录，文件名为raw_data.csv
        output_csv = input_dir.parent / "raw_data.csv"
    
    # 处理题型筛选参数
    allowed_question_types = None
    if hasattr(args, 'question_types') and args.question_types is not None:
        # 如果命令行指定了空列表（通过 --question-types ""），则保留所有题型
        if len(args.question_types) == 1 and args.question_types[0] == "":
            allowed_question_types = []
        else:
            allowed_question_types = args.question_types
    
    # 处理已存在CSV文件路径
    existing_csv = None
    if args.existing_csv:
        existing_csv = Path(args.existing_csv)
        if not existing_csv.exists():
            logging.warning(f"指定的已存在CSV文件不存在: {existing_csv}，将不进行过滤")
            existing_csv = None
    
    # 执行转换
    convert_raw_data_to_csv(
        input_dir,
        output_csv,
        include_columns=args.columns,
        file_patterns=args.patterns,
        resume=args.resume,
        allowed_question_types=allowed_question_types,
        existing_csv=existing_csv
    )
    
    logging.info("转换完成")
    
    # 统计两个CSV文件的信息
    # 确定已存在CSV文件路径（优先使用参数指定的，否则使用默认值）
    existing_csv_for_stats = existing_csv
    if existing_csv_for_stats is None and DEFAULT_EXISTING_CSV:
        existing_csv_for_stats = Path(DEFAULT_EXISTING_CSV)
    
    if output_csv.exists():
        logging.info("=" * 80)
        logging.info("文件统计信息：")
        if existing_csv_for_stats and existing_csv_for_stats.exists():
            log_csv_statistics(existing_csv_for_stats, "已存在CSV文件")
        else:
            logging.info(f"已存在CSV文件 ({DEFAULT_EXISTING_CSV}): 文件不存在")
        log_csv_statistics(output_csv, "输出CSV文件")
        logging.info("=" * 80)


def log_csv_statistics(csv_path: Path, file_label: str):
    """
    统计CSV文件的信息并输出日志
    
    Args:
        csv_path: CSV文件路径
        file_label: 文件标签（用于日志输出）
    """
    if not csv_path.exists():
        logging.info(f"{file_label} ({csv_path}): 文件不存在")
        return
    
    try:
        question_ids = set()
        total_rows = 0
        total_questions = 0  # 按question_id去重后的题目数量
        
        with open(csv_path, 'r', encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                total_rows += 1
                question_id = row.get("question_id", "")
                if question_id:
                    question_ids.add(str(question_id))
        
        total_questions = len(question_ids)
        
        logging.info(f"{file_label}:")
        logging.info(f"  文件路径: {csv_path}")
        logging.info(f"  总行数: {total_rows}")
        logging.info(f"  不同question_id数量: {total_questions}")
        logging.info(f"  总问题数: {total_questions}")
        
    except Exception as e:
        logging.warning(f"统计{file_label}失败 {csv_path}: {e}")


if __name__ == '__main__':
    main()
