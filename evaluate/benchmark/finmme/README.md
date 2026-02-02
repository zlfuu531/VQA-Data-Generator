# FinMME 数据集转换和评测工具

本模块用于将 FinMME 数据集转换为 `evaluate_py` 评测框架需要的标准格式，并调用框架进行评测。

## 功能说明

- 从本地数据集目录加载 FinMME 数据集
- 自动处理字段映射和格式转换：
  - `question_type` 从英文映射到中文（single_choice → 单选题，multiple_choice → 多选题，numerical → 问答题）
  - `options` 从字符串格式转换为字典格式（如 "A: 16% B: 20%" → {"A": "16%", "B": "20%"}）
- 自动保存图片到本地（evaluate_py 需要图片路径）
- 调用 evaluate_py 框架进行评测
- 输出和日志都在本文件夹下

## 安装依赖

```bash
pip install datasets pillow
```

## 快速开始

### 1. 转换数据（自动完成）

评测脚本会自动检查并转换数据，也可以手动转换：

```bash
cd /home/zenglingfeng/qa_pipline12-7/evaluate/benchmark/finmme
python convert_data.py --output finmme_converted.jsonl
```

### 2. 运行评测

```bash
# 使用默认配置（expert 用户画像，qwen3-vl-32b-thinking 模型）
./run_eval_finmme.sh

# 或指定参数
export EVAL_MODELS="qwen3-vl-32b-thinking"
export PROFILES="expert"
./run_eval_finmme.sh
```

### 3. 自定义配置

可以通过环境变量自定义配置：

```bash
# 指定模型
export EVAL_MODELS="qwen3-vl-32b-thinking,InternVL3_5-30B-A3B"

# 指定用户画像
export PROFILES="expert,retail,beginner"

# 限制评测数量（用于测试）
export LIMIT="100"

# 其他配置
export WORKERS=24          # 并发线程数
export LOG_LEVEL="INFO"    # 日志级别
export RESUME="true"       # 断点续跑

./run_eval_finmme.sh
```

## 字段映射说明

### 核心字段映射

| evaluate_py 字段 | FinMME 字段 | 转换说明 |
|-----------------|------------|---------|
| question_id | id 或 idx | 直接使用 |
| image_id | id 或 idx | 与 question_id 相同 |
| question | question_text | 直接使用 |
| question_type | question_type | **英文映射到中文**：single_choice → 单选题，multiple_choice → 多选题，numerical → 问答题 |
| answer | answer | 直接使用 |
| options | options | **字符串转换为字典**：`"A: 16% B: 20%"` → `{"A": "16%", "B": "20%"}` |
| image_path | image | 从 PIL Image 对象保存到本地 |

### 其他字段

其他所有字段（如 `knowledge_domain`, `unit`, `tolerance`, `verified_caption`, `related_sentences` 等）会原样保留在转换后的数据中，但不参与评测和评分，仅用于统计和分析。

## 文件结构

```
finmme/
├── convert_data.py          # 数据转换脚本
├── convert_finmme.py        # 命令行入口（简化版）
├── data_mapping.py          # 字段映射配置
├── run_eval_finmme.sh       # 评测脚本（主入口）
├── README.md                # 本文档
├── __init__.py              # 模块初始化
├── finmme_converted.jsonl   # 转换后的数据文件（自动生成）
├── outputs/                 # 评测输出目录
│   └── {profile}/
│       └── {model_name}/
│           └── finmme_eval_results.jsonl
├── logs/                    # 日志目录
│   └── eval_*.log
└── images/                  # 图片保存目录（自动生成）
    └── {image_id}.png
```

## 输出说明

评测结果会保存在：
- `outputs/{profile}/{model_name}/finmme_eval_results.jsonl`

日志会保存在：
- `logs/eval_*.log`

## 注意事项

1. **图片保存**：默认会将图片保存到 `images/` 子目录，因为 evaluate_py 框架需要文件路径才能加载图片。

2. **question_type 映射**：
   - `single_choice` → `单选题`
   - `multiple_choice` → `多选题`
   - `numerical` → `问答题`（数值题当作问答题处理）

3. **options 转换**：
   - 支持两种格式：
     - 换行分隔：`"A: xxx\nB: yyy\nC: zzz"`
     - 空格分隔：`"A: xxx B: yyy C: zzz"`
   - 自动转换为字典格式：`{"A": "xxx", "B": "yyy", "C": "zzz"}`

4. **数据转换**：评测脚本会自动检查并转换数据，如果转换后的数据文件已存在，会直接使用，不会重复转换。

5. **断点续跑**：默认启用断点续跑功能，如果评测中断，重新运行会从中断处继续。

## 参考

- [FinMME 数据集](https://huggingface.co/datasets/luojunyu/FinMME)
- [FinMME GitHub](https://github.com/luo-junyu/FinMME)
