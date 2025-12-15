## QA Pipeline - 多模态问答评估框架

一个用于 **多模态问答生成 → 难度分级 → 金融领域评测** 的完整流水线框架。

整个项目包含三个核心模块：
- **Module1 - 问题生成**：从图片生成结构化问答数据
- **Module2 - 难度分级**：基于多模型回答结果进行难度分级
- **Evaluate - 金融评测**：对模型在多模态金融题目上的表现进行评测

## 📋 目录

- [整体架构](#整体架构)
- [快速开始](#快速开始)
- [项目结构](#项目结构)
- [Module1 - 问题生成](#module1---问题生成)
- [Module2 - 难度分级](#module2---难度分级)
- [Evaluate - 金融领域评测框架](#evaluate---金融领域评测框架)

## 🧱 整体架构

```text
            +------------------------+
            |  图片/原始多模态数据   |
            +-----------+------------+
                        |
                        v
        +---------------+----------------+
        |   Module1 - 问题生成（图片→问答） |
        +---------------+----------------+
                        |
                        v
        +---------------+----------------+
        |   Module2 - 难度分级（问答→L1-L4） |
        +---------------+----------------+
                        |
                        v
        +---------------+----------------------------+
        | Evaluate - 金融领域评测（多模型表现评估）    |       
        +-------------------------------------------+
```

三步即可完成从 **原始图文 → 问答生成 → 难度分级 → 模型评测** 的全流程。

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置验证（全局）

在运行任何模块之前，建议先运行配置验证脚本检查所有配置：

```bash
python check_config.py
```

该脚本会检查：
- ✅ 所有必需的环境变量和 API Key（供 Module2 & Evaluate 使用）
- ✅ 输入文件路径是否存在
- ✅ 输出目录权限
- ✅ 配置文件格式是否正确

### 3. 配置 API Key（全局）

在项目根目录创建 `.env` 文件：

```bash
# API Keys（供 Module2 和 Evaluate 使用）
api1=your_dashscope_api_key
api2=your_volces_api_key
api3=your_openrouter_api_key
api4=your_siliconflow_api_key
```

### 4. 各模块一键运行 shell

- **Module1（问题生成）**
  - 进入目录：`cd module1`
  - 运行脚本：`bash github_template.sh`

- **Module2（难度分级）**
  - 直接在项目根目录运行：

    ```bash
    bash module2/main.sh
    ```

  - 如果只想**重试 Module2 中 error 文件里的错误题目**（不重新跑全部题），可以使用：

    ```bash
    bash module2/重试错误题请使用这个.sh
    ```

    该脚本会：
    - 读取已有输出目录（包含 `L1-L4`、`summary`、`error.json/jsonl`）
    - 仅对 `error` 中的题目做补答/重试
    - 重新写回新的 `L1-L4`、`error` 与 `summary`

  - 框架默认配置豆包、GLM、Qwen的三个VL模型，如需更改，请设置`module2/config.py`

- **Evaluate（金融评测）**
  - 进入目录：`cd evaluate`
  - 运行脚本：`bash run_eval.sh`
  - 更改需要评测的模型配置，请设置`evaluate/config.py`



## 📁 项目结构

```
qa_pipline/
├── module1/                    # 问题生成模块
│   ├── qa_make.py             # 主程序（问题生成逻辑）
│   ├── github_template.sh      # 运行脚本模板
│   └── 计算价格.py            # 辅助工具
│
├── module2/                    # 难度分级模块
│   ├── main.py                 # 主程序入口
│   ├── main.sh                 # 运行脚本
│   ├── config.py               # API配置（模型地址、名称等）
│   ├── model_evaluation.py     # 核心评估逻辑
│   ├── answer_comparison.py    # 答案对比模块
│   ├── judge.py                # 评判模型（包含prompt）
│   ├── classifier.py           # 难度分级模块
│   ├── logger.py               # 日志记录
│   └── models/                 # 模型调用接口
│       ├── model1.py           # 模型1的prompt模板和API调用
│       ├── model2.py           # 模型2的prompt模板和API调用
│       └── model3.py           # 模型3的prompt模板和API调用
│
├── evaluate/                   # 金融领域评测框架
│   ├── main.py                 # 主程序入口
│   ├── run_eval.sh             # 运行脚本
│   ├── config.py               # 模型配置
│   ├── data_loader.py          # 数据加载
│   ├── data_converter.py       # 数据转换
│   ├── model_api.py            # 模型API调用
│   ├── judge.py                # 答案评判
│   ├── prompts.py              # 提示词模板
│   └── README.md               # 详细文档
│
├── utils.py                    # 工具函数
├── utils_common.sh             # 通用工具函数（统一错误提示格式）
├── check_config.py             # 配置验证脚本
├── .env.example                # 环境变量配置示例
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

# API配置（示例）
API_BASE="https://dashscope.aliyuncs.com/compatible-mode/v1"
API_KEY="your-api-key"
MODEL="qwen3-vl-plus"

# 题目生成参数
IMAGE_TYPE="all"              # 图片类型：pure_image/pure_text/mixed/splice/stacked/all
QUESTION_TYPE="essay"         # 问题类型：single_choice/multiple_choice/true_false/essay/等
NUM=1                         # 每张图片生成几个问题
ROUNDS=3                      # 多轮对话轮数（仅多轮题型）

# 性能参数
WORKERS=10                    # 并发线程数
BATCH=10                      # 批量写入大小
RESUME=true                   # 断点续传
```

### 功能特性

- ✅ 支持 JSON/JSONL 输入输出
- ✅ 支持多种问题类型（单选、多选、判断、问答、多轮对话等）
- ✅ 支持图片类型筛选
- ✅ 断点续传（自动跳过已处理图片）
- ✅ 多线程并发处理
- ✅ 自动重试失败请求

### 注意事项

1. **输出格式选择**：
   - `jsonl`：逐行追加，适合大量数据，batch参数仅用于刷新频率
   - `json`：批量保存，需要batch参数控制，适合小批量测试

2. **断点续传**：
   - `RESUME=true`：自动跳过已处理的 `image_id`
   - `RESUME=false`：全新运行，会生成 `_v2` 版本文件

### Prompt 修改

- **问题生成 Prompt**：`qa_pipline/module1/qa_make.py`

## 🔍 Module2 - 难度分级

### 功能说明

Module2 用于对问答对进行难度分级。输入 Module1 的输出文件，调用多个模型回答问题，使用评判模型判断答案正确性，并根据模型表现自动进行难度分级（L1-L4）。

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
```jsonl
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
api1="212"
api2="212"
api3="323"
api4="212"
```

#### 4. 错误样本重试脚本（`module2/重试错误题请使用这个.sh`）

当已经完整跑完一次 Module2，并在输出目录中生成了 `L1-L4` 与 `error` 文件时，如果只想对错误题目进行重跑，可使用该脚本：

```bash
bash module2/重试错误题请使用这个.sh
```

关键配置与行为：
- **OUTPUT_DIR**：必填，指向已有输出目录，需包含 `L1-L4` 与 `error.json/jsonl`
- **自动识别格式**：若存在 `L1.jsonl` 则按 `jsonl` 模式，否则按 `json` 模式
- 只重试 `error` 文件中的题目，对已有正常题目**不会重复调用模型**
- 重试完成后，会重新写回该目录下的 `L1-L4`、`error` 与 `summary`
- 对已在 `L1-L4` 中存在的旧残留错误条目会自动清理

### 功能特性

- ✅ 支持 JSON/JSONL 输入输出
- ✅ 多模型并行评估（用于难度分级）
- ✅ 自动答案评判（使用评判模型）
- ✅ 自动难度分级（L1-L4，核心功能）
- ✅ 断点续传（自动跳过已处理样本）
- ✅ 错误重试（自动重试失败的样本）
- ✅ 实时写入（JSONL格式）
- ✅ 统计汇总（summary.json）

### 注意事项

1. **输出格式选择**：
   - `jsonl`：实时写入，适合大量数据，无需buffer
   - `json`：批量保存，需要设置 `BATCH_SIZE`

2. **断点续传**：
   - `RE_EVALUATE=false`：自动跳过已处理的 `question_id`
   - `RE_EVALUATE=true`：重新评估，生成新版本目录

3. **错误处理**：
   - 重试成功的样本会自动从 `error.jsonl` 中删除
   - 只保留仍然失败的记录

### Prompt 修改

- **回答模型**：`qa_pipline/module2/models/` 目录下的模型文件
- **裁判模型**：`qa_pipline/module2/judge.py`

## 🎯 Evaluate - 金融领域评测框架

支持多种用户画像、多种模型、多种题型的金融领域评测系统。

### 快速开始

编辑 `evaluate/run_eval.sh` 文件，配置参数后运行：

```bash
cd evaluate
bash run_eval.sh
```


### 配置说明

#### 1. 脚本配置（run_eval.sh）

主要配置项：

```bash
# 输入文件
INPUT_FILE="/path/to/input.jsonl"

# 输出文件名（只需文件名，不要路径）
OUTPUT_FILE="eval_results.json"
# 文件将保存在：./outputs/{profile}/{model_name}/{OUTPUT_FILE}

# 要评测的模型（逗号分隔）
EVAL_MODELS="qwenvlmax"

# 用户画像（逗号分隔）
PROFILES="expert"
# 可选：beginner, retail, expert, expert_cot

# 断点续跑
RESUME=true

# 限制处理数量（空字符串表示全部）
LIMIT="5"
```

#### 2. 模型配置（config.py）

##### API 服务商配置

```python
BASE_URL_CONFIG = {
    "dashscope": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key": _get_env("api1"),  # 从环境变量读取
    },
    # ... 其他服务商
}
```

##### 模型定义

```python
MODEL_DEFINITIONS = {
    "qwenvlmax": {
        "base_url_key": "dashscope",
        "model": "qwen-vl-max",
        "max_tokens": 8192,
        "timeout": 600,
    },
    # ... 其他模型
}
```

##### 设置要评测的模型

在 `run_eval.sh` 中设置：
```bash
EVAL_MODELS="qwenvlmax,doubao,GLM"
```

或在环境变量中设置：
```bash
export EVAL_MODELS="qwenvlmax,doubao,GLM"
```

### 输入文件格式

#### 支持格式
- JSON：`[{...}, {...}]` 或 `{"items": [{...}, {...}]}`
- JSONL：每行一个 JSON 对象
- CSV：表格格式（自动转换）

#### 字段说明

| 字段名 | 类型 | 必需 | 说明 | 示例 |
|--------|------|------|------|------|
| `question_id` | string | ✅ | 问题唯一标识符 | `"question_001"` |
| `question` | string/dict | ✅ | 问题文本。单轮为字符串，多轮为字典（`{"round1": "...", "round2": "..."}`） | `"根据图表，选择正确答案"` |
| `answer` | string/dict | ✅ | 标准答案。单轮为字符串，多轮为字典（`{"round1": "...", "round2": "..."}`） | `"B"` 或 `{"round1": "A", "round2": "B"}` |
| `image_id` | string | ❌ | 图片唯一标识符 | `"image_001"` |
| `image_path` | string/list | ❌ | 图片路径。支持：1) 单路径字符串；2) 逗号分隔字符串；3) 路径数组。支持本地路径和URL（以`http://`或`https://`开头）混合使用 | `"/path/to/image.png"` 或 `"/path/to/img1.png, http://example.com/img2.png"` 或 `["/path/to/img1.png", "http://example.com/img2.png"]` |
| `image_type` | string | ❌ | 图片类型分类 | `"chart"`, `"diagram"`, `"text"` |
| `question_type` | string | ❌ | 题型。支持：`单选题`/`多选题`/`判断题`/`问答题`/`多轮单选题`/`多轮问答题`（中英文均可）。未指定时自动识别：有`options`→选择题，无`options`→问答题 | `"单选题"` 或 `"single_choice"` |
| `options` | dict | ❌ | 选项字典（选择题需要）。键为选项标识（如A/B/C/D），值为选项内容 | `{"A": "选项A", "B": "选项B", "C": "选项C", "D": "选项D"}` |
| `scenario` | string | ❌ | 场景分类（用于统计） | `"金融分析"` |
| `capability` | string | ❌ | 能力分类（用于统计） | `"图表理解"` |
| `difficulty` | string | ❌ | 难度分类（用于统计） | `"简单"`, `"中等"`, `"困难"` |
| `source` | string | ❌ | 数据来源（用于统计） | `"数据集A"` |

**注意：**
- `question_id` 和 `id` 都可以使用，优先使用 `question_id`
- `image_path` 支持本地路径（相对/绝对）和URL（以`http://`或`https://`开头），系统会自动识别
- 多张图片会在第一轮对话时全部输入给模型
- 多轮问答会自动识别：当`question`和`answer`都是字典且包含`round*`键时，自动判断为多轮格式

#### 多张图片格式示例

| 格式 | JSON/JSONL | CSV |
|------|------------|-----|
| **字符串（逗号分隔）** | `"image_path": "/path/to/img1.png, http://example.com/img2.png"` | `image_path`<br>`/path/to/img1.png;http://example.com/img2.png` |
| **数组格式** | `"image_path": ["/path/to/img1.png", "http://example.com/img2.png"]` | - |

#### 完整字段示例

**单轮问题：**
```json
{
  "question_id": "question_001",
  "image_id": "image_001",
  "image_path": "/path/to/image.png",
  "image_type": "chart",
  "question_type": "单选题",
  "question": "根据图表，选择正确答案：",
  "options": {
    "A": "选项A",
    "B": "选项B",
    "C": "选项C",
    "D": "选项D"
  },
  "answer": "B",
  "scenario": "金融分析",
  "capability": "图表理解",
  "difficulty": "中等",
  "source": "数据集A"
}
```

**多张图片示例：**
```json
{
  "question_id": "question_003",
  "image_id": "image_003",
  "image_path": "/path/to/image1.png, /path/to/image2.png, https://example.com/image3.png",
  "question": "对比这三张图表，分析...",
  "answer": "..."
}
```

**多轮问题：**
```json
{
  "question_id": "question_002",
  "image_id": "image_002",
  "question_type": "多轮问答题",
  "question": {
    "round1": "第一轮问题",
    "round2": "第二轮问题",
    "round3": "第三轮问题"
  },
  "answer": {
    "round1": "第一轮答案",
    "round2": "第二轮答案",
    "round3": "第三轮答案"
  },
  "image_path": "/path/to/image.png"
}
```

#### 题型说明

支持的题型（中英文均可）：
- `单选题` / `single_choice`
- `多选题` / `multiple_choice`
- `判断题` / `true_false`
- `问答题` / `essay`
- `多轮单选题` / `multi_round_single_choice`
- `多轮问答题` / `multi_round_essay`

**注意：**
- 如果没有 `question_type` 字段：
  - 有 `options` → 自动识别为选择题
  - 无 `options` → 自动识别为问答题

### 输出文件格式

#### 输出位置

```
./outputs/
  ├── {profile}/
  │   ├── {model_name}/
  │   │   └── {output_file}
```

例如：`./outputs/expert/qwenvlmax/eval_results.json`

#### 输出结构

```json
{
  "metadata": {
    "timestamp": "2024-01-01T12:00:00",
    "input_file": "/path/to/input.json",
    "total_items": 100,
    "evaluated_items": 100,
    "enabled_models": ["qwenvlmax"],
    "profiles": ["expert"]
  },
  "statistics": {
    "total_items": 100,
    "profiles": {
      "expert": {
        "total": 100,
        "correct": 85,
        "accuracy": 0.85,
        "models": {
          "qwenvlmax": {
            "total": 100,
            "correct": 85,
            "accuracy": 0.85
          }
        }
      }
    }
  },
  "results": [
    {
      "question_id": "question_001",
      "question_type": "单选题",
      "question": "...",
      "answer": "B",
      "profiles": {
        "expert": {
          "models": {
            "qwenvlmax": {
              "model_name": "qwen-vl-max",
              "extracted_answer": "B",
              "is_correct": true,
              "reasoning": "答案一致",
              "response_time": 2.5,
              "judge_time": 0.8
            }
          }
        }
      }
    }
  ]
}
```

### 用户画像

| 画像 | 说明 | 特点 |
|------|------|------|
| `beginner` | 金融小白 | 完全不懂金融，用简单易懂的方式思考 |
| `retail` | 散户投资者 | 有一定金融基础，用专业但易懂的方式思考 |
| `expert` | 金融专家 | 资深专家，用深度专业的方式思考 |
| `expert_cot` | 金融专家（CoT） | 专家 + 思维链推理方法 |

### 功能特性

- ✅ **多用户画像**：支持4种用户画像，每种使用不同的提示词
- ✅ **多模型支持**：可同时评测多个模型
- ✅ **多题型支持**：支持6种题型，自动识别
- ✅ **多轮对话**：支持多轮问答，使用对话历史
- ✅ **智能评判**：使用裁判模型自动评判答案正确性
- ✅ **断点续跑**：支持中断后继续评测
- ✅ **详细统计**：提供按画像、模型、题型的统计信息

### 环境变量

在 `.env` 文件或环境变量中设置 API Key：

```bash
api1=your_dashscope_api_key
api2=your_volces_api_key
api3=your_openrouter_api_key
api4=your_siliconflow_api_key
```

### 注意事项

1. **API Key**：确保配置了正确的 API Key
2. **图片路径**：确保图片路径正确且可访问
3. **断点续跑**：启用 `RESUME=true` 时，必须设置 `OUTPUT_FILE`
4. **输出目录**：固定为 `./outputs`，按用户画像和模型分类组织

### 依赖

```bash
pip install openai tqdm python-dotenv
```

## 📄 License
