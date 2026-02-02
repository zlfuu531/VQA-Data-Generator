import json
import os
from pathlib import Path

def convert_image_path_to_absolute(img_path: str) -> str:
    """
    将相对路径转换为绝对路径
    原始格式: "./MultiFinance/images/1334-1.png"
    目标格式: "/nfsdata-117/project/finvlr1/Benchmark/FinMMR/images/1334-1.png"
    """
    if not img_path:
        return img_path
    
    # 如果是相对路径
    if img_path.startswith("./") or img_path.startswith("../"):
        # 提取文件名
        filename = os.path.basename(img_path)
        # 构建绝对路径
        absolute_path = f"/nfsdata-117/project/finvlr1/Benchmark/FinMMR/images/{filename}"
        return absolute_path
    # 如果已经是绝对路径，直接返回
    elif img_path.startswith("/"):
        return img_path
    # 其他情况，尝试拼接
    else:
        filename = os.path.basename(img_path)
        absolute_path = f"/nfsdata-117/project/finvlr1/Benchmark/FinMMR/images/{filename}"
        return absolute_path

def extract_answer(row: dict):
    """提取答案，优先使用 ground_truth，如果没有则使用 answer，返回字符串格式（不做任何处理，原样转换）"""
    answer = row.get('ground_truth')
    if answer is None:
        answer = row.get('answer')
    
    # 如果答案不存在，返回 None
    if answer is None:
        return None
    
    # 直接转换为字符串，不做任何格式处理，保持原样
    return str(answer)

def get_difficulty(row: dict) -> str:
    """从 grade 字段或 difficulty 字段获取难度"""
    grade = row.get('grade', '').lower()
    if grade in ['easy', 'medium', 'hard']:
        return grade
    
    # 如果 grade 是其他格式，尝试从 difficulty 数值推断
    difficulty_num = row.get('difficulty')
    if difficulty_num is not None:
        # 根据难度数值范围判断（需要根据实际数据调整）
        if isinstance(difficulty_num, (int, float)):
            if difficulty_num < 2.0:
                return 'easy'
            elif difficulty_num < 3.0:
                return 'medium'
            else:
                return 'hard'
    
    return 'unknown'

def build_user_input(context: str, question: str) -> str:
    """
    按照 FinMMR 的格式拼接 context 和 question
    参考 easy_validation_cot_prompt.json 中的 user_input 格式
    """
    if not context or context.strip() == "<image 1>":
        # 如果 context 为空或只是占位符，只返回问题
        return f"Question: {question}\n\nLet's think step by step to answer the given question."
    else:
        # 按照 FinMMR 的格式拼接
        return f"The following question context is provided for your reference.{context}\n\n\nQuestion: {question}\n\nLet's think step by step to answer the given question."

dataset = []
base_dir = '/nfsdata-117/project/finvlr1/Benchmark/FinMMR/data'

# 处理 validation 数据
validation_files = [
    ('easy', f'{base_dir}/validation/easy_validation.json'),
    ('medium', f'{base_dir}/validation/medium_validation.json'),
    ('hard', f'{base_dir}/validation/hard_validation.json'),
]

for difficulty, file_path in validation_files:
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            for idx, row in enumerate(data, 1):
                # 提取答案
                answer = extract_answer(row)
                if answer is None:
                    continue  # 跳过没有答案的数据
                
                # 提取图片路径并转换为绝对路径
                images = row.get('images', [])
                image_paths = [convert_image_path_to_absolute(img) for img in images]
                
                # 获取难度
                row_difficulty = get_difficulty(row)
                # 如果从 grade 获取失败，使用传入的 difficulty
                if row_difficulty == 'unknown':
                    row_difficulty = difficulty
                
                # 生成 question_id（使用原始 question_id 或生成新的）
                question_id = row.get('question_id', f'{row_difficulty}-validation-{idx-1}')
                
                # 提取并拼接 context 和 question
                context = row.get('context', '')
                question = row.get('question', '')
                user_input = build_user_input(context, question)
                
                result = {
                    'question_id': question_id,
                    'answer': answer,
                    'image_path': image_paths,
                    'difficulty': row_difficulty,
                    'scenario': 'validation',
                    'question': user_input  # 添加拼接后的完整输入
                }
                dataset.append(result)

# 处理 test 数据
test_files = [
    ('easy', f'{base_dir}/test/easy_test.json'),
    ('medium', f'{base_dir}/test/medium_test.json'),
    ('hard', f'{base_dir}/test/hard_test.json'),
]

for difficulty, file_path in test_files:
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            for idx, row in enumerate(data, 1):
                # 提取答案
                answer = extract_answer(row)
                if answer is None:
                    continue  # 跳过没有答案的数据
                
                # 提取图片路径并转换为绝对路径
                images = row.get('images', [])
                image_paths = [convert_image_path_to_absolute(img) for img in images]
                
                # 获取难度
                row_difficulty = get_difficulty(row)
                # 如果从 grade 获取失败，使用传入的 difficulty
                if row_difficulty == 'unknown':
                    row_difficulty = difficulty
                
                # 生成 question_id（使用原始 question_id 或生成新的）
                question_id = row.get('question_id', f'{row_difficulty}-test-{idx-1}')
                
                # 提取并拼接 context 和 question
                context = row.get('context', '')
                question = row.get('question', '')
                user_input = build_user_input(context, question)
                
                result = {
                    'question_id': question_id,
                    'answer': answer,
                    'image_path': image_paths,
                    'difficulty': row_difficulty,
                    'scenario': 'test',
                    'question': user_input  # 添加拼接后的完整输入
                }
                dataset.append(result)

# 保存结果
output_file = '/home/zenglingfeng/qa_pipline12-7/evaluate/benchmark/finmmr/FinMMR_data_origin.json'
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(dataset, f, ensure_ascii=False, indent=4)

# 统计信息
validation_count = sum(1 for d in dataset if d['scenario'] == 'validation')
test_count = sum(1 for d in dataset if d['scenario'] == 'test')
easy_count = sum(1 for d in dataset if d['difficulty'] == 'easy')
medium_count = sum(1 for d in dataset if d['difficulty'] == 'medium')
hard_count = sum(1 for d in dataset if d['difficulty'] == 'hard')

print(f"总共处理了 {len(dataset)} 条数据")
print(f"Validation: {validation_count} 条, Test: {test_count} 条")
print(f"Easy: {easy_count} 条, Medium: {medium_count} 条, Hard: {hard_count} 条")
print(f"数据已保存到: {output_file}")

