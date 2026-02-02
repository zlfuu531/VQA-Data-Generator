import json

dataset = []
count = 0  # 全局计数器，用于生成唯一的 question_id

# 处理 easy 难度级别
count_easy = 0  # easy 难度级别的计数器
# 处理 easy validation 文件
with open('/nfsdata-117/project/finvlr1/Benchmark/FinMMR/data/easy_validation_cot_prompt.json', 'r', encoding='utf-8') as f:
    easy = json.load(f)
    for row in easy:
        count += 1
        count_easy += 1
        result = {
            'question_id': f'easy_{count_easy}',
            'count_easy': count_easy,
            'question': row['user_input'],
            'answer': row['ground_truth'],
            'image_path': row['images'],
            'difficulty': 'easy'
        }
        dataset.append(result)

# 处理 easy test 文件
with open('/nfsdata-117/project/finvlr1/Benchmark/FinMMR/data/easy_test_cot_prompt.json', 'r', encoding='utf-8') as f:
    easy_2 = json.load(f)
    for row in easy_2:
        if 'answer' in row.keys():
            count += 1
            count_easy += 1
            result = {
                'question_id': f'easy_{count_easy}',
                'count_easy': count_easy,
                'question': row['user_input'],
                'answer': row['answer'],
                'image_path': row['images'],
                'difficulty': 'easy'
            }
            dataset.append(result)

# 处理 medium 难度级别
count_medium = 0  # medium 难度级别的计数器
# 处理 medium validation 文件
with open('/nfsdata-117/project/finvlr1/Benchmark/FinMMR/data/medium_validation_cot_prompt.json', 'r', encoding='utf-8') as f:
    medium = json.load(f)
    for row in medium:
        count += 1
        count_medium += 1
        result = {
            'question_id': f'medium_{count_medium}',
            'count_medium': count_medium,
            'question': row['user_input'],
            'answer': row['ground_truth'],
            'image_path': row['images'],
            'difficulty': 'medium'
        }
        dataset.append(result)

# 处理 medium test 文件
with open('/nfsdata-117/project/finvlr1/Benchmark/FinMMR/data/medium_test_cot_prompt.json', 'r', encoding='utf-8') as f:
    medium_2 = json.load(f)
    for row in medium_2:
        if 'answer' in row.keys():
            count += 1
            count_medium += 1
            result = {
                'question_id': f'medium_{count_medium}',
                'count_medium': count_medium,
                'question': row['user_input'],
                'answer': row['answer'],
                'image_path': row['images'],
                'difficulty': 'medium'
            }
            dataset.append(result)

# 处理 hard 难度级别
count_hard = 0  # hard 难度级别的计数器
# 处理 hard validation 文件
with open('/nfsdata-117/project/finvlr1/Benchmark/FinMMR/data/hard_validation_cot_prompt.json', 'r', encoding='utf-8') as f:
    hard = json.load(f)
    for row in hard:
        count += 1
        count_hard += 1
        result = {
            'question_id': f'hard_{count_hard}',
            'count_hard': count_hard,
            'question': row['user_input'],
            'answer': row['ground_truth'],
            'image_path': row['images'],
            'difficulty': 'hard'
        }
        dataset.append(result)

# 处理 hard test 文件
with open('/nfsdata-117/project/finvlr1/Benchmark/FinMMR/data/hard_test_cot_prompt.json', 'r', encoding='utf-8') as f:
    hard_2 = json.load(f)
    for row in hard_2:
        if 'answer' in row.keys():
            count += 1
            count_hard += 1
            result = {
                'question_id': f'hard_{count_hard}',
                'count_hard': count_hard,
                'question': row['user_input'],
                'answer': row['answer'],
                'image_path': row['images'],
                'difficulty': 'hard'
            }
            dataset.append(result)

# 保存结果
with open('/nfsdata-117/project/finvlr1/Benchmark/FinMMR/FinMMR_data.json', 'w', encoding='utf-8') as f:
    json.dump(dataset, f, ensure_ascii=False, indent=4)

print(f"总共处理了 {count} 条数据")
print(f"Easy: {count_easy} 条, Medium: {count_medium} 条, Hard: {count_hard} 条")