"""
统计每个模型在不同fintype下的正确率。
每一行数据（即使是同一question_id的不同轮次）都被视为一个独立的题目进行统计。
"""
import pandas as pd
import logging
from collections import defaultdict

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def get_model_names(df: pd.DataFrame) -> list:
    """从DataFrame中自动识别模型列。"""
    # 定义元数据列，这些列不应被视为模型
    meta_columns = {
        'question_id', 'round', 'question', 'answer', 'question_type', 
        'image_type', 'image_path', 'original_image_path', 'profile', 
        'scenario', 'difficulty', 'language', 'fintype'
    }
    # 返回不在元数据列中的所有列名
    return [col for col in df.columns if col not in meta_columns]

def analyze_fintype_accuracy(excel_path: str):
    """
    分析Excel文件中每个模型在不同fintype下的正确率。
    """
    try:
        logging.info(f"正在读取文件: {excel_path}")
        df = pd.read_excel(excel_path, engine='openpyxl')
    except FileNotFoundError:
        logging.error(f"文件未找到: {excel_path}")
        return

    if "fintype" not in df.columns:
        logging.error("文件中未找到 'fintype' 列")
        return

    model_names = get_model_names(df)
    if not model_names:
        logging.error("未找到任何模型列")
        return
    
    logging.info(f"找到 {len(model_names)} 个模型列: {model_names}")
    
    # 统计结果字典
    stats = defaultdict(lambda: defaultdict(lambda: {"total": 0, "correct": 0}))
    
    # 遍历每一行数据。这里的逻辑确保了每一行都被视为一个独立的题目。
    for idx, row in df.iterrows():
        fintype = row.get("fintype")
        
        if pd.isna(fintype) or fintype == "":
            continue
        
        for model in model_names:
            value = row.get(model)
            
            if pd.isna(value):
                continue
            
            try:
                # 统一处理和转换评测结果（0或1）
                if isinstance(value, str):
                    value_str = value.strip().lower()
                    if value_str in ["1", "true"]:
                        numeric_value = 1
                    elif value_str in ["0", "false"]:
                        numeric_value = 0
                    else:
                        numeric_value = float(value_str)
                else:
                    numeric_value = float(value)
                
                # 统计总数和正确数
                stats[model][fintype]["total"] += 1
                if numeric_value == 1:
                    stats[model][fintype]["correct"] += 1
            except (ValueError, TypeError):
                logging.warning(f"行 {idx+2}, 模型 {model}: 值 '{value}' 无法转换为数值，已跳过。")
                continue
    
    print_results(stats, model_names)

def print_results(stats, model_names):
    """打印格式化的统计结果。"""
    all_fintypes = sorted({f for model_stat in stats.values() for f in model_stat.keys()})

    # 1. 按fintype分组，横向对比所有模型
    print("\n" + "="*100)
    print("按fintype分组统计（横向对比所有模型）")
    print("="*100)
    for fintype in all_fintypes:
        print(f"\n【fintype: {fintype}】")
        print("-" * 100)
        fintype_results = []
        for model in model_names:
            data = stats.get(model, {}).get(fintype, {"total": 0, "correct": 0})
            total = data["total"]
            correct = data["correct"]
            accuracy = (correct / total * 100) if total > 0 else 0.0
            fintype_results.append((model, total, correct, accuracy))
        
        # 按正确率排序
        fintype_results.sort(key=lambda x: x[3], reverse=True)
        for model, total, correct, accuracy in fintype_results:
            print(f"  {model:35s} | 总数: {total:5d} | 正确数: {correct:5d} | 正确率: {accuracy:6.2f}%")

    # 2. 汇总统计，计算各场景正确率的平均值
    print("\n" + "="*100)
    print("汇总统计（各场景正确率的平均值）")
    print("="*100)
    print("注意：此处的正确率是各fintype正确率的平均值，而非总正确率")
    print("-" * 100)
    
    summary_results = []
    for model in model_names:
        model_stats = stats.get(model, {})
        if not model_stats:
            continue
            
        # 计算每个fintype的正确率
        fintype_accuracies = []
        for fintype, data in model_stats.items():
            total = data["total"]
            correct = data["correct"]
            if total > 0:  # 只统计有数据的fintype
                accuracy = (correct / total * 100)
                fintype_accuracies.append(accuracy)
        
        # 计算平均正确率
        avg_accuracy = sum(fintype_accuracies) / len(fintype_accuracies) if fintype_accuracies else 0.0
        total_questions = sum(data["total"] for data in model_stats.values())
        correct_questions = sum(data["correct"] for data in model_stats.values())
        
        summary_results.append((model, total_questions, correct_questions, avg_accuracy))
    
    # 按平均正确率排序
    summary_results.sort(key=lambda x: x[3], reverse=True)
    
    # 打印表头
    print(f"{'排名':<6s} | {'模型名称':<35s} | {'总题数':>8s} | {'正确数':>8s} | {'平均正确率':>12s}")
    print("-" * 100)
    
    # 打印每个模型的结果
    for rank, (model, total, correct, avg_accuracy) in enumerate(summary_results, 1):
        print(f"{rank:<6d} | {model:<35s} | {total:>8d} | {correct:>8d} | {avg_accuracy:>11.2f}%")
    
    print("\n" + "="*100)
    logging.info("统计完成")

if __name__ == "__main__":
    # 请将此路径替换为你的Excel文件路径
    excel_path = "/home/zenglingfeng/qa_pipline12-7/evaluate/benchmark/visfineval/visfineval-1-8.xlsx"
    #excel_path = "/home/zenglingfeng/qa_pipline12-7/evaluate/benchmark/visfineval/vis-fintype.xlsx"
    analyze_fintype_accuracy(excel_path)
