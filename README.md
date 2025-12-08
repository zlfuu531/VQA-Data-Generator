# QA Pipeline - 多模态问答评估框架

一个用于多模态问答生成与模型评估的完整流水线框架。

## 📋 目录

- [快速开始](#快速开始)
- [项目结构](#项目结构)
- [Module1 - 问题生成](#module1---问题生成)
- [Module2 - 模型评估](#module2---模型评估)
- [Prompt 修改](#prompt-修改)

## 🚀 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 配置 API Key

在项目根目录创建 `.env` 文件：

```bash
# Module1 使用的 API Key（在运行脚本中配置）
# Module2 使用的 API Key
QA_PIPELINE_MODEL2_API_KEY=your_api_key_here
QA_PIPELINE_MODEL3_API_KEY=your_api_key_here
QA_PIPELINE_JUDGE_API_KEY=your_api_key_here
```

## 📁 项目结构

```
qa_pipline/
├── module1/                    # 问题生成模块
│   ├── qa_make.py             # 主程序（问题生成逻辑）
│   ├── github_template.sh      # 运行脚本模板
│   └── 计算价格.py            # 辅助工具
│
├── module2/                    # 模型评估模块
│   ├── main.py                 # 主程序入口
│   ├── main.sh                 # 运行脚本
│   ├── config.py               # API配置（模型地址、名称等）
│   ├── model_evaluation.py     # 核心评估逻辑
│   ├── answer_comparison.py    # 答案对比模块
│   ├── judge.py                # 评判模型（包含prompt）
│   ├── classifier.py           # 难度分级模块
│   └── logger.py               # 日志记录
│
├── models/                     # 模型调用接口
│   ├── model1.py              # 模型1的prompt模板和API调用
│   ├── model2.py              # 模型2的prompt模板和API调用
│   └── model3.py              # 模型3的prompt模板和API调用
│
├── utils.py                    # 工具函数
├── requirements.txt            # 依赖包
├── .env                        # API Key配置（不提交到git）
└── README.md                   # 本文档
```

## 📝 Module1 - 问题生成

### 功能说明

Module1 用于基于图片生成问答对。输入图片列表，输出包含问题、答案、选项等字段的 JSON/JSONL 文件。

### 运行方式

```bash
cd module1
bash github_template.sh
```


### 输入格式

支持 `.json` 和 `.jsonl` 格式，包含图片信息：

```json
[
  {
    "id": "img001",
    "image_path": "path/to/image.jpg",
    "image_type": "财报"
  }
]
```

### 输出格式

输出包含 9 个标准字段的问答对：

```jsonl
{"question_id": "q001", "question": "图中2022年的营收是多少？", "answer": "500亿元", "question_type": "问答", "image_path": "path/to/image.jpg", "image_type": "财报", "options": null, "qa_make_process": "...", "image_id": "img001"}
```

**输出字段说明：**
- `question_id`: 问题唯一标识
- `question`: 问题内容
- `answer`: 标准答案
- `question_type`: 问题类型（single_choice/multiple_choice/true_false/essay等）
- `image_path`: 图片路径
- `image_type`: 图片类型
- `options`: 选项（选择题时使用）
- `qa_make_process`: 生成过程（可选）
- `image_id`: 原始图片ID

### 配置说明

在 `github_template.sh` 中修改：

```bash
# 输入输出
INPUT_FILE="/path/to/input.json"
OUTPUT_FILE="../output/module1/output.jsonl"

# API配置
API_BASE="https://dashscope.aliyuncs.com/compatible-mode/v1"
API_KEY="your-api-key"
MODEL="qwen3-vl-plus"

# 题目生成参数
IMAGE_TYPE="all"              # 图片类型：pure_image/pure_text/mixed/splice/all
QUESTION_TYPE="essay"         # 问题类型：single_choice/multiple_choice/true_false/essay/multi_round_*
NUM=1                         # 每张图片生成几个问题
ROUNDS=3                      # 多轮对话轮数（仅多轮题型）

# 性能参数
WORKERS=10                    # 并发线程数
BATCH=10                      # 批量写入大小
RESUME=true                   # 断点续传
```

## 🔍 Module2 - 难度分级

### 功能说明

Module2 用于评估多个模型在问答任务上的表现。输入 Module1 的输出文件，调用多个模型回答问题，使用评判模型判断答案正确性，并自动进行难度分级。

### 运行方式

```bash
bash module2/main.sh
```

### 输入格式

Module1 的输出文件（支持 `.json` 和 `.jsonl`）：

```jsonl
{"question_id": "q001", "question": "图中2022年的营收是多少？", "answer": "500亿元", "question_type": "问答", "image_path": "path/to/image.jpg", "image_type": "财报", "options": null}
```

### 输出格式

输出目录结构：

```
output/module2/测试/
├── L1.jsonl          # L1难度级别结果
├── L2.jsonl          # L2难度级别结果
├── L3.jsonl          # L3难度级别结果
├── L4.jsonl          # L4难度级别结果
├── error.jsonl       # 模型生成出错的题目
└── summary.json      # 统计汇总
```

**输出示例（L1.jsonl）：**
```json
{
  "id": "q001",
  "question": "图中2022年的营收是多少？",
  "answer": "500亿元",
  "model1": {
    "answer": "500亿",
    "match_gt": true,
    "enabled": true,
    "process": "...",
    "model_name": "doubao-seed-1-6-251015"
  },
  "model2": {...},
  "model3": {...},
  "classification": {
    "level": "L1",
    "category": "..."
  },
  "comparison": {
    "agreement_with_gt": 2
  }
}
```

### 配置说明

#### 1. 运行参数（`module2/main.sh`）

```bash
# 输入输出
INPUT_FILE="../output/module1/测试.jsonl"
OUTPUT_DIR="../output/module2/测试"
OUTPUT_FORMAT="jsonl"  # json 或 jsonl

# 运行参数
WORKERS=40         # 并发线程数
BATCH_SIZE=40      # 批量保存大小（仅json格式）
DEBUG_MODE=true   # 调试模式
RE_EVALUATE=true  # 是否重新评估
```

#### 2. API 配置（`module2/config.py`）

修改模型地址、名称、参数等



#### 3. API Key（`.env` 文件）

```bash
# 模型API Key
QA_PIPELINE_MODEL2_API_KEY=sk-xxx
QA_PIPELINE_MODEL3_API_KEY=sk-xxx

# 评判模型API Key
QA_PIPELINE_JUDGE_API_KEY=sk-xxx
```



## ✏️ Prompt 修改

### module1修改地址：qa_pipline/module1/qa_make.py

### module1修改地址：
回答模型：qa_pipline/models
裁判模型：qa_pipline/module2/judge.py


## 📝 注意事项

### Module1

1. **输出格式选择**：
   - `jsonl`：逐行追加，适合大量数据，batch参数仅用于刷新频率
   - `json`：批量保存，需要batch参数控制，适合小批量测试

2. **断点续传**：
   - `RESUME=true`：自动跳过已处理的 `image_id`
   - `RESUME=false`：全新运行，会生成 `_v2` 版本文件

### Module2

1. **输出格式选择**：
   - `jsonl`：实时写入，适合大量数据，无需buffer
   - `json`：批量保存，需要设置 `BATCH_SIZE`

2. **断点续传**：
   - `RE_EVALUATE=false`：自动跳过已处理的 `question_id`
   - `RE_EVALUATE=true`：重新评估，生成新版本目录

3. **错误处理**：
   - 重试成功的样本会自动从 `error.jsonl` 中删除
   - 只保留仍然失败的记录

## 📄 License

MIT License
