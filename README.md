# Module1: 问题生成模块

## 📋 目录

- [概述](#概述)
- [快速开始](#快速开始)
- [工作流程](#工作流程)
- [字段设置与输出](#字段设置与输出)
- [提示词设计](#提示词设计)
- [配置参数](#配置参数)
- [扩展指南](#扩展指南)

---

## 概述

Module1 是 QA 流水线的第一个模块，负责根据图片内容生成各种类型的问题。支持多种图片类型和问题类型，采用模块化设计，易于扩展。

### 主要特性

- ✅ 支持 4 种图片类型：`pure_image`、`pure_text`、`mixed`、`splice`
- ✅ 支持 6 种问题类型：单选题、多选题、判断题、问答题、多轮单选题、多轮问答题
- ✅ 可配置的图片类型筛选（支持 `all` 处理所有类型）
- ✅ 断点续传功能
- ✅ 多线程并发处理
- ✅ 思考模式支持（提取模型推理过程）
- ✅ 完整的日志记录
- ✅ 实时进度显示

---

## 快速开始

### 1. 安装依赖

```bash
pip install openai tqdm  # tqdm 可选，用于进度条显示
```

### 2. 配置参数

编辑 `main.sh` 文件，设置相关参数：

```bash
# ================= 🔧 基础路径配置 =================
INPUT_FILE="/path/to/input.json"
OUTPUT_FILE="/path/to/output.json"
LOG_DIR="../logs"

# ================= 🤖 模型与API配置 =================
API_BASE="your-url"
API_KEY="your-api-key"
MODEL="model-name"

# ================= 🎛️ 生成参数 =================
IMAGE_TYPE="all"          # 图片类型: pure_image, pure_text, mixed, splice，all
QUESTION_TYPE="essay"       # 问题类型: single_choice, multiple_choice, true_false, essay问答, multi_round_single_choice, multi_round_essay
NUM=2                       # 每张图片生成几个问题
ROUNDS=2                    # 多轮对话的轮数（仅用于多轮对话题型）
TEMP=0.7                    # 温度参数
TOKENS=8192                 # 最大Token数
#如需更细节的参数调节可添加至./qa_make.py中调用部分
                 # 最大Token数

# ================= 🚀 性能配置 =================
WORKERS=4                   # 并发线程数
BATCH=4                    # json批量写入大小

# ================= 🛑 其他配置 =================
RESUME=true                # 是否断点续传 (true/false)，false即重新处理图片重新生成json文件
LIMIT="20"                   # 限制处理的图片数量，设置为空字符串 "" 则处理全部
ENABLE_THINKING=false       # 是否启用思考模式 (true/false)，启用后会提取 reasoning_content

```

### 3. 运行

```bash
bash main.sh
```
---

## 工作流程

### 详细步骤

1. **读取输入文件**
   - 解析 JSON 文件，获取图片列表
   - 每个图片项包含：`id`、`image_path`、`image_type`（可选）

2. **图片类型筛选**
   - 如果 `image_type="all"`：处理所有图片
   - 否则：只处理匹配指定类型的图片
   - 支持从输入数据中读取 `image_type` 字段

3. **断点续传**
   - 读取输出文件，提取已处理的 `image_id`
   - 跳过已处理的图片，继续处理未完成的

4. **并发处理**
   - 使用 `ThreadPoolExecutor` 并发处理多张图片
   - 每个线程处理一张图片的多个问题

5. **问题生成**
   - 对每张图片，调用 `generate_qa_data()` 生成 N 个问题
   - 每个问题通过独立的 API 调用生成（多次对话）
   - 每次调用使用相同的提示词模板

6. **响应解析**
   - 解析模型返回的 JSON
   - 提取 `question`、`answer`、`options`、`qa_make_process`
   - 处理多轮对话的字典格式

7. **推理内容合并**
   - 如果启用 `enable_thinking`，提取 `reasoning_content`
   - 合并到 `qa_make_process` 字段

8. **输出保存**
   - 批量写入输出文件（达到 `batch_size` 时写入）
   - 记录所有模型响应到日志文件

---

## 字段设置与输出

### 输入格式

输入 JSON 文件格式：image_type可以写成type

```json
[
    {
        "id": "1",
        "image_path": "/path/to/image1.jpg",
        "image_type": "mixed"  // 可选，如果不提供则使用命令行参数
    },
    {
        "id": "2",
        "image_path": "/path/to/image2.jpg",
        "image_type": "pure_image"
    }
]
```

### 输出格式

#### 单轮对话题型（单选题、多选题、判断题、问答题）

```json
{
    "image_id": "1",
    "image_path": "/path/to/image1.jpg",
    "image_type": "mixed",
    "question_id": "1_essay_0",
    "question_type": "问答题",
    "question": "问题内容...",
    "options": null,  // 问答题为 null，选择题为 {"A": "...", "B": "...", "C": "...", "D": "..."}
    "answer": "正确答案",  // 单选题为 "A"，多选题为 "AB"，判断题为 "true"/"false"
    "qa_make_process": "推理过程..."
}
```

#### 多轮对话题型（多轮单选题、多轮问答题）

```json
{
    "image_id": "1",
    "image_path": "/path/to/image1.jpg",
    "image_type": "mixed",
    "question_id": "1_multi_round_single_choice_0",
    "question_type": "多轮单选题",
    "question": {
        "round1": "第一轮问题...",
        "round2": "第二轮问题...",
        "round3": "第三轮问题..."
    },
    "options": {
        "round1": {"A": "...", "B": "...", "C": "...", "D": "..."},
        "round2": {"A": "...", "B": "...", "C": "...", "D": "..."},
        "round3": {"A": "...", "B": "...", "C": "...", "D": "..."}
    },  // 多轮问答题为 null
    "answer": {
        "round1": "A",
        "round2": "B",
        "round3": "C"
    },
    "qa_make_process": {
        "round1": "第一轮推理过程...",
        "round2": "第二轮推理过程...",
        "round3": "第三轮推理过程..."
    }
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `image_id` | string | 图片ID，与图片路径绑定，同一张图片的所有问题使用相同的 `image_id` |
| `image_path` | string | 图片文件路径 |
| `image_type` | string | 图片类型：`pure_image`、`pure_text`、`mixed`、`splice` |
| `question_id` | string | 问题ID，格式：`{image_id}_{question_type}_{question_index}`，每个问题唯一 |
| `question_type` | string | 问题类型的中文名称 |
| `question` | string/dict | 问题内容。单轮对话为字符串，多轮对话为字典 `{"round1": "...", "round2": "..."}` |
| `options` | dict/null | 选项。单选题/多选题为字典，判断题/问答题为 `null`。多轮对话为字典格式 |
| `answer` | string/dict | 答案。单轮对话为字符串，多轮对话为字典格式 |
| `qa_make_process` | string/dict | 推理过程。单轮对话为字符串，多轮对话为字典格式。如果启用思考模式，会包含模型的 `reasoning_content` |

### 思考模式（enable_thinking）

当启用 `--enable_thinking` 时，`qa_make_process` 字段会包含模型的推理内容：

**单轮对话格式：**
```
【模型思考推理过程】
{reasoning_content}

【问题解答过程】
{模型生成的问题解答过程}
```

**多轮对话格式：**
每轮的 `qa_make_process` 都会包含推理内容：
```json
{
    "round1": "【模型思考推理过程】\n{reasoning_content}\n\n【问题解答过程】\n{round1_process}",
    "round2": "【模型思考推理过程】\n{reasoning_content}\n\n【问题解答过程】\n{round2_process}"
}
```

---

## 提示词设计

### 提示词结构

提示词由两部分组成：

1. **图片类型出题逻辑**（`get_image_type_prompt`）
   - 角色定义
   - 图片类型说明
   - 图片特点
   - 出题重点
   - 出题要求

2. **题目类型要求**（`get_question_type_specific_requirements`）
   - 格式规范
   - 输出格式示例

### 图片类型

#### 可以直接更改图片类型对应的prompt

#### pure_image（纯图片类型）

#### pure_text（纯文本类型）

#### mixed（混合类型）

#### splice（拼接类型）

### 问题类型输出格式

#### 目前有6 种问题类型：单选题、多选题、判断题、问答题、多轮单选题、多轮问答题

---

## 扩展指南

### 添加新的图片类型

1. 在 `IMAGE_TYPES` 列表中添加新类型：
```python
IMAGE_TYPES = ["pure_image", "pure_text", "mixed", "splice", "new_type"]
```

2. 在 `get_image_type_prompt()` 函数中添加对应的提示词：
```python
prompts = {
    # ... 现有类型 ...
    "new_type": f"""
你是一位专业的视觉推理评测出题专家。请基于这张图片的内容，设计一道【{question_type_name_cn}】。

**图片类型**: new_type（新类型）
**图片特点**：...
**出题重点**：...
**出题要求**：
1. **深度推理**：...
2. **特殊要求**：...
3. **思维链**：...
"""
}
```

### 添加新的问题类型

1. 在 `QUESTION_TYPES` 字典中添加映射：
```python
QUESTION_TYPES = {
    # ... 现有类型 ...
    "new_question_type": "新问题类型"
}
```

2. 在 `get_question_type_specific_requirements()` 函数中添加格式要求：
```python
requirements = {
    # ... 现有类型 ...
    "new_question_type": """
**格式规范**：新问题类型的格式要求...

**输出格式**：
请严格返回一个 JSON 对象（不是数组）：
{{
    "question_type": "新问题类型",
    "question": "问题内容...",
    "options": ...,
    "qa_make_process": "推理过程...",
    "answer": "答案"
}}
"""
}
```

3. 在 `generate_single_qa()` 函数中添加对应的解析逻辑（如果需要特殊处理）

4. 更新 argparse 的 choices：
```python
parser.add_argument("--question_type", 
                   choices=[..., "new_question_type"],
                   ...)
```


## 注意事项

1. **image_id 与 question_id**
   - `image_id`：只与图片路径绑定，同一张图片的所有问题使用相同的 `image_id`
   - `question_id`：每个问题唯一，格式为 `{image_id}_{question_type}_{question_index}`（0开始计数）

2. **断点续传**
   - 基于 `image_id` 判断是否已处理
   - 如果图片已处理，会跳过该图片的所有问题生成

3. **多轮对话**
   - 轮数通过 `--rounds` 参数配置
   - 输出格式为字典，包含 `round1`、`round2` 等字段



## 常见问题

### Q: 如何只处理特定类型的图片？

A: 设置 `--image_type` 为具体类型（如 `mixed`），系统会自动筛选匹配的图片。

### Q: 如何处理所有类型的图片？

A: 设置 `--image_type all`，系统会处理所有图片，不进行筛选。

---


