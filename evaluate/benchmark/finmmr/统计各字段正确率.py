"""
统计每个模型在不同scenario（test/validation）和difficulty下的正确率
"""
import pandas as pd
import logging
from pathlib import Path
from collections import defaultdict

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# 基础字段列（非模型列）
BASE_COLUMNS = {
    "question_id", "round", "question", "answer", "question_type",
    "image_type", "image_path", "original_image_path", "profile",
    "scenario", "capability", "difficulty", "source", "language",
    "option_A", "option_B", "option_C", "option_D", "fintype"
}


def get_model_columns(df: pd.DataFrame) -> list:
    """
    从DataFrame中自动识别模型列（排除基础字段列）
    
    Args:
        df: DataFrame
        
    Returns:
        模型列名列表
    """
    all_columns = set(df.columns)
    model_columns = sorted(all_columns - BASE_COLUMNS)
    return model_columns


def convert_to_score(value) -> int:
    """
    将值转换为得分（0或1）
    
    Args:
        value: 原始值
        
    Returns:
        0或1，如果无法转换则返回None
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
    
    Args:
        excel_path: 输入Excel文件路径
        output_path: 输出Excel文件路径（如果为None，则自动生成）
    """
    # 读取Excel文件
    logging.info(f"正在读取文件: {excel_path}")
    df = pd.read_excel(excel_path, engine='openpyxl')
    
    # 打印列名，方便调试
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
    
    # 标准化difficulty值（转换为小写，便于匹配）
    difficulty_mapping = {}
    for diff in difficulties:
        diff_str = str(diff).strip().lower()
        difficulty_mapping[diff_str] = diff
    
    # 定义difficulty的标准顺序（如果存在）
    difficulty_order = ["easy", "medium", "hard", "simple", "normal", "complex"]
    sorted_difficulties = []
    for std_diff in difficulty_order:
        for diff_key, diff_value in difficulty_mapping.items():
            if std_diff in diff_key or diff_key in std_diff:
                sorted_difficulties.append(diff_value)
                break
    
    # 添加未匹配的difficulty值
    for diff in difficulties:
        if diff not in sorted_difficulties:
            sorted_difficulties.append(diff)
    
    logging.info(f"找到的scenario值: {sorted(scenarios)}")
    logging.info(f"找到的difficulty值: {sorted_difficulties}")
    
    # 统计结果字典
    # 结构: {model_name: {scenario: {difficulty: {"total": count, "correct": count}}}}
    stats = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: {"total": 0, "correct": 0})))
    
    # 遍历每一行数据
    for idx, row in df.iterrows():
        scenario = row.get("scenario")
        difficulty = row.get("difficulty")
        
        # 跳过scenario或difficulty为空的行
        if pd.isna(scenario) or scenario == "":
            continue
        if pd.isna(difficulty) or difficulty == "":
            continue
        
        # 标准化scenario和difficulty（转换为字符串并去除空格）
        scenario = str(scenario).strip()
        difficulty = str(difficulty).strip()
        
        # 对每个模型进行统计
        for model in model_columns:
            value = row.get(model)
            score = convert_to_score(value)
            
            # 跳过无法转换的值
            if score is None:
                continue
            
            # 统计
            stats[model][scenario][difficulty]["total"] += 1
            if score == 1:
                stats[model][scenario][difficulty]["correct"] += 1
    
    # 构建结果表格
    # 动态生成列：根据实际的scenario和difficulty值
    result_rows = []
    
    for model in model_columns:
        row_data = {"模型": model}
        
        # 为每个scenario和difficulty组合生成统计
        for scenario in sorted(scenarios):
            scenario_str = str(scenario).strip()
            for difficulty in sorted_difficulties:
                difficulty_str = str(difficulty).strip()
                
                # 获取统计数据
                total = stats[model].get(scenario_str, {}).get(difficulty_str, {}).get("total", 0)
                correct = stats[model].get(scenario_str, {}).get(difficulty_str, {}).get("correct", 0)
                accuracy = (correct / total * 100) if total > 0 else 0.0
                
                # 添加列
                col_prefix = f"{scenario_str}_{difficulty_str}"
                row_data[f"{col_prefix}_正确率"] = f"{accuracy:.2f}%"
                row_data[f"{col_prefix}_正确数"] = correct
                row_data[f"{col_prefix}_总数"] = total
        
        # 统计总体（所有scenario合并）
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
    logging.info(f"正在保存结果到: {output_path}")
    result_df.to_excel(output_path, index=False, engine='openpyxl')
    logging.info(f"结果已保存，共 {len(result_df)} 个模型")
    
    # 打印结果摘要
    print("\n" + "="*150)
    print("统计结果摘要（按scenario分组）")
    print("="*150)
    
    # 按scenario打印
    for scenario in sorted(scenarios):
        scenario_str = str(scenario).strip()
        print(f"\n【{scenario_str}】")
        print("-" * 150)
        
        # 构建表头
        header_parts = [f"{'模型':<40s}"]
        for difficulty in sorted_difficulties:
            difficulty_str = str(difficulty).strip()
            header_parts.append(f"{scenario_str}_{difficulty_str}")
        header = " | ".join(header_parts)
        print(header)
        print("-" * 150)
        
        # 打印每行数据
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
    
    # 构建表头
    header_parts = [f"{'模型':<40s}"]
    for difficulty in sorted_difficulties:
        difficulty_str = str(difficulty).strip()
        header_parts.append(f"total_{difficulty_str}")
    header = " | ".join(header_parts)
    print(header)
    print("-" * 150)
    
    # 打印每行数据
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


if __name__ == "__main__":
    excel_path = "/home/zenglingfeng/qa_pipline12-7/evaluate/benchmark/finmmr/finmmr所有数据-去空.xlsx"
    output_path = "/home/zenglingfeng/qa_pipline12-7/evaluate/benchmark/finmmr/finmmr统计结果.xlsx"
    
    try:
        analyze_scenario_difficulty_accuracy(excel_path, output_path)
    except Exception as e:
        logging.error(f"处理文件时出错: {e}", exc_info=True)
