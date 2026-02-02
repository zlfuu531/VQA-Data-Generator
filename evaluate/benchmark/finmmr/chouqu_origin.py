import json
import os

dataset = []
count = 0  # 全局计数器

# 处理 easy 难度级别
count_easy = 0

# 处理 easy validation 文件
validation_file = '/nfsdata-117/project/finvlr1/Benchmark/FinMMR/data/validation/easy_validation.json'
if os.path.exists(validation_file):
    with open(validation_file, 'r', encoding='utf-8') as f:
        easy_validation = json.load(f)
        for row in easy_validation:
            count += 1
            count_easy += 1
            # 优先使用 ground_truth，如果没有则使用 answer
            answer = row.get('ground_truth')
            if answer is None:
                answer = row.get('answer')
            # 如果 answer 是字符串，尝试转换为数值
            if isinstance(answer, str):
                try:
                    # 尝试转换为浮点数
                    answer = float(answer)
                    # 如果是整数，转换为整数
                    if answer.is_integer():
                        answer = int(answer)
                except ValueError:
                    pass  # 保持字符串格式
            
            result = {
                'question_id': f'easy_{count_easy}',
                'count_easy': count_easy,
                'question': row.get('question', ''),
                'answer': answer,
                'image_path': row.get('images', []),
                'difficulty': 'easy'
            }
            dataset.append(result)

# 处理 easy test 文件
test_file = '/nfsdata-117/project/finvlr1/Benchmark/FinMMR/data/test/easy_test.json'
if os.path.exists(test_file):
    with open(test_file, 'r', encoding='utf-8') as f:
        easy_test = json.load(f)
        for row in easy_test:
            # 检查是否有答案字段
            if 'ground_truth' in row or 'answer' in row:
                count += 1
                count_easy += 1
                # 优先使用 ground_truth，如果没有则使用 answer
                answer = row.get('ground_truth')
                if answer is None:
                    answer = row.get('answer')
                # 如果 answer 是字符串，尝试转换为数值
                if isinstance(answer, str):
                    try:
                        answer = float(answer)
                        if answer.is_integer():
                            answer = int(answer)
                    except ValueError:
                        pass
                
                result = {
                    'question_id': f'easy_{count_easy}',
                    'count_easy': count_easy,
                    'question': row.get('question', ''),
                    'answer': answer,
                    'image_path': row.get('images', []),
                    'difficulty': 'easy'
                }
                dataset.append(result)

# 处理 medium 难度级别
count_medium = 0

# 处理 medium validation 文件
validation_file = '/nfsdata-117/project/finvlr1/Benchmark/FinMMR/data/validation/medium_validation.json'
if os.path.exists(validation_file):
    with open(validation_file, 'r', encoding='utf-8') as f:
        medium_validation = json.load(f)
        for row in medium_validation:
            count += 1
            count_medium += 1
            answer = row.get('ground_truth')
            if answer is None:
                answer = row.get('answer')
            if isinstance(answer, str):
                try:
                    answer = float(answer)
                    if answer.is_integer():
                        answer = int(answer)
                except ValueError:
                    pass
            
            result = {
                'question_id': f'medium_{count_medium}',
                'count_medium': count_medium,
                'question': row.get('question', ''),
                'answer': answer,
                'image_path': row.get('images', []),
                'difficulty': 'medium'
            }
            dataset.append(result)

# 处理 medium test 文件
test_file = '/nfsdata-117/project/finvlr1/Benchmark/FinMMR/data/test/medium_test.json'
if os.path.exists(test_file):
    with open(test_file, 'r', encoding='utf-8') as f:
        medium_test = json.load(f)
        for row in medium_test:
            if 'ground_truth' in row or 'answer' in row:
                count += 1
                count_medium += 1
                answer = row.get('ground_truth')
                if answer is None:
                    answer = row.get('answer')
                if isinstance(answer, str):
                    try:
                        answer = float(answer)
                        if answer.is_integer():
                            answer = int(answer)
                    except ValueError:
                        pass
                
                result = {
                    'question_id': f'medium_{count_medium}',
                    'count_medium': count_medium,
                    'question': row.get('question', ''),
                    'answer': answer,
                    'image_path': row.get('images', []),
                    'difficulty': 'medium'
                }
                dataset.append(result)

# 处理 hard 难度级别
count_hard = 0

# 处理 hard validation 文件
validation_file = '/nfsdata-117/project/finvlr1/Benchmark/FinMMR/data/validation/hard_validation.json'
if os.path.exists(validation_file):
    with open(validation_file, 'r', encoding='utf-8') as f:
        hard_validation = json.load(f)
        for row in hard_validation:
            count += 1
            count_hard += 1
            answer = row.get('ground_truth')
            if answer is None:
                answer = row.get('answer')
            if isinstance(answer, str):
                try:
                    answer = float(answer)
                    if answer.is_integer():
                        answer = int(answer)
                except ValueError:
                    pass
            
            result = {
                'question_id': f'hard_{count_hard}',
                'count_hard': count_hard,
                'question': row.get('question', ''),
                'answer': answer,
                'image_path': row.get('images', []),
                'difficulty': 'hard'
            }
            dataset.append(result)

# 处理 hard test 文件
test_file = '/nfsdata-117/project/finvlr1/Benchmark/FinMMR/data/test/hard_test.json'
if os.path.exists(test_file):
    with open(test_file, 'r', encoding='utf-8') as f:
        hard_test = json.load(f)
        for row in hard_test:
            if 'ground_truth' in row or 'answer' in row:
                count += 1
                count_hard += 1
                answer = row.get('ground_truth')
                if answer is None:
                    answer = row.get('answer')
                if isinstance(answer, str):
                    try:
                        answer = float(answer)
                        if answer.is_integer():
                            answer = int(answer)
                    except ValueError:
                        pass
                
                result = {
                    'question_id': f'hard_{count_hard}',
                    'count_hard': count_hard,
                    'question': row.get('question', ''),
                    'answer': answer,
                    'image_path': row.get('images', []),
                    'difficulty': 'hard'
                }
                dataset.append(result)

# 保存结果
output_file = '/home/zenglingfeng/qa_pipline12-7/evaluate/benchmark/finmmr/FinMMR_data_origin.json'
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(dataset, f, ensure_ascii=False, indent=4)

print(f"总共处理了 {count} 条数据")
print(f"Easy: {count_easy} 条, Medium: {count_medium} 条, Hard: {count_hard} 条")
print(f"数据已保存到: {output_file}")

