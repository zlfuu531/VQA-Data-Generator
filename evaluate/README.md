# 金融领域评测框架

支持多种用户画像、多种模型、多种题型的金融领域评测系统。

## 快速开始

### 方式一：使用脚本运行（推荐）

编辑 `run_eval.sh` 文件，配置参数后运行：

```bash
bash run_eval.sh
```

### 方式二：直接运行 Python

```bash
python -m evaluate.main \
    --input_file /path/to/input.json \
    --output_file eval_results.json \
    --profiles expert \
    --resume
```

## 配置说明

### 1. 脚本配置（run_eval.sh）

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

### 2. 模型配置（config.py）

#### API 服务商配置

```python
BASE_URL_CONFIG = {
    "dashscope": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key": _get_env("api1"),  # 从环境变量读取
    },
    # ... 其他服务商
}
```

#### 模型定义

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

#### 设置要评测的模型

在 `run_eval.sh` 中设置：
```bash
EVAL_MODELS="qwenvlmax,doubao,GLM"
```

或在环境变量中设置：
```bash
export EVAL_MODELS="qwenvlmax,doubao,GLM"
```

## 输入文件格式

### 支持格式
- JSON：`[{...}, {...}]` 或 `{"items": [{...}, {...}]}`
- JSONL：每行一个 JSON 对象
- CSV：表格格式（自动转换）

### 字段说明

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

### 多张图片格式示例

| 格式 | JSON/JSONL | CSV |
|------|------------|-----|
| **字符串（逗号分隔）** | `"image_path": "/path/to/img1.png, http://example.com/img2.png"` | `image_path`<br>`/path/to/img1.png;http://example.com/img2.png` |
| **数组格式** | `"image_path": ["/path/to/img1.png", "http://example.com/img2.png"]` | - |

### 完整字段示例

**单轮问题：**
```json
{
  "question_id": "question_001",
  "image_id": "image_001",
  "image_path": "/path/to/image.png",     // 单张图片，或多张图片用逗号分隔
  "image_type": "chart",
  "question_type": "单选题",              // 题型：单选题/多选题/判断题/问答题/多轮单选题/多轮问答题
  "question": "根据图表，选择正确答案：",
  "options": {                            // 选项（选择题必需，问答题可为null）
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
  "image_path": "/path/to/image.png"     // 多张图片会在第一轮全部输入（自动识别为多轮格式）
}
```

### 题型说明

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

## 输出文件格式

### 输出位置

```
./outputs/
  ├── {profile}/
  │   ├── {model_name}/
  │   │   └── {output_file}
```

例如：`./outputs/expert/qwenvlmax/eval_results.json`

### 输出结构

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

## 用户画像

| 画像 | 说明 | 特点 |
|------|------|------|
| `beginner` | 金融小白 | 完全不懂金融，用简单易懂的方式思考 |
| `retail` | 散户投资者 | 有一定金融基础，用专业但易懂的方式思考 |
| `expert` | 金融专家 | 资深专家，用深度专业的方式思考 |
| `expert_cot` | 金融专家（CoT） | 专家 + 思维链推理方法 |

## 功能特性

- ✅ **多用户画像**：支持4种用户画像，每种使用不同的提示词
- ✅ **多模型支持**：可同时评测多个模型
- ✅ **多题型支持**：支持6种题型，自动识别
- ✅ **多轮对话**：支持多轮问答，使用对话历史
- ✅ **智能评判**：使用裁判模型自动评判答案正确性
- ✅ **断点续跑**：支持中断后继续评测
- ✅ **详细统计**：提供按画像、模型、题型的统计信息

## 环境变量

在 `.env` 文件或环境变量中设置 API Key：

```bash
api1=your_dashscope_api_key
api2=your_volces_api_key
api3=your_openrouter_api_key
api4=your_siliconflow_api_key
```

## 注意事项

1. **API Key**：确保配置了正确的 API Key
2. **图片路径**：确保图片路径正确且可访问
3. **断点续跑**：启用 `RESUME=true` 时，必须设置 `OUTPUT_FILE`
4. **输出目录**：固定为 `./outputs`，按用户画像和模型分类组织

## 依赖

```bash
pip install openai tqdm python-dotenv
```
