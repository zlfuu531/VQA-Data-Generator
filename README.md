# QA 流水线框架

一个完整的 QA（问答）生成与评估流水线，包含问题生成和模型评估两个核心模块。

## 📋 目录

- [概述](#概述)
- [快速开始](#快速开始)
- [Module1: 问题生成模块](#module1-问题生成模块)
- [Module2: 模型评估模块](#module2-模型评估模块)
- [工作流程](#工作流程)

---

## 概述

本框架提供从问题生成到模型评估的完整 QA 流水线：

- **Module1**：根据图片内容生成各种类型的问题
- **Module2**：调用多个模型回答问题，进行答案比对和难度分级

### 主要特性

- ✅ 支持 4 种图片类型：`pure_image`、`pure_text`、`mixed`、`splice`
- ✅ 支持 6 种问题类型：单选题、多选题、判断题、问答题、多轮单选题、多轮问答题
- ✅ 多模型评估与答案比对
- ✅ 自动难度分级（L1-L4）
- ✅ 断点续传功能
- ✅ 多线程并发处理
- ✅ 完整的日志记录

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 运行 Module1（问题生成）

编辑 `module1/main.sh`，配置输入输出路径和 API 参数：

```bash
cd module1
bash main.sh
```

### 3. 运行 Module2（模型评估）

编辑 `module2/main.sh`，配置输入文件（Module1 的输出）和输出目录：

```bash
cd module2
bash main.sh
```

---

## Module1: 问题生成模块

### 功能

根据图片内容生成各种类型的问题，支持单轮和多轮对话。

### 输入格式

```json
[
    {
        "id": "1",
        "image_path": "/path/to/image1.jpg",
        "image_type": "mixed"
    }
]
```

### 输出格式

```json
{
    "image_id": "1",
    "image_path": "/path/to/image1.jpg",
    "image_type": "mixed",
    "question_id": "1_essay_0",
    "question_type": "问答题",
    "question": "问题内容...",
    "options": null,
    "answer": "正确答案",
    "qa_make_process": "推理过程..."
}
```

### 主要配置参数

- `IMAGE_TYPE`: 图片类型（`pure_image`、`pure_text`、`mixed`、`splice`、`all`）
- `QUESTION_TYPE`: 问题类型（`single_choice`、`multiple_choice`、`true_false`、`essay`、`multi_round_single_choice`、`multi_round_essay`）
- `NUM`: 每张图片生成的问题数量
- `WORKERS`: 并发线程数
- `RESUME`: 是否断点续传

详细配置请参考 `module1/main.sh`。

---

## Module2: 模型评估模块

### 功能

调用多个模型（model1、model2、model3）回答问题，使用裁判模型进行答案比对，并通过分类器进行难度分级。

### 工作流程

1. **模型调用**：对每个问题调用多个模型生成答案
2. **答案比对**：使用裁判模型（Judge）评估模型答案的正确性
3. **难度分级**：根据模型表现将问题分为 L1-L4 四个难度级别
4. **结果输出**：按难度级别分类保存结果

### 输出结构

```
output/module2/module2_result/
├── L1.json          # 难度1级别的题目
├── L2.json          # 难度2级别的题目
├── L3.json          # 难度3级别的题目
├── L4.json          # 难度4级别的题目
├── error.json       # 模型生成出错的题目
└── summary.json     # 统计信息
```

### 主要配置参数

- `INPUT_FILE`: Module1 的输出文件路径
- `OUTPUT_DIR`: 输出目录
- `RE_EVALUATE`: 是否重新评估（`true`/`false`）
- `WORKERS`: 并发线程数
- `BATCH_SIZE`: 批量保存大小

模型配置（API 地址、模型名称等）在 `module2/config.py` 中设置。

---

## 工作流程

```
图片输入
    ↓
[Module1] 问题生成
    ├─ 图片类型筛选
    ├─ 问题生成（支持多种题型）
    └─ 输出：问题 + 答案 + 推理过程
    ↓
[Module2] 模型评估
    ├─ 多模型调用（model1, model2, model3）
    ├─ 答案比对（Judge）
    ├─ 难度分级（L1-L4）
    └─ 输出：按难度分类的结果
```

---

## 注意事项

1. **Module1 → Module2**：Module2 的输入必须是 Module1 的输出格式
2. **断点续传**：两个模块都支持断点续传，可随时中断和恢复
3. **配置管理**：Module1 的配置在 `main.sh` 中，Module2 的模型配置在 `config.py` 中
4. **日志记录**：所有模块都会生成详细的日志文件，便于调试和追踪

---

## 扩展指南

### 添加新的图片类型

在 `module1/qa_make.py` 中：
1. 在 `IMAGE_TYPES` 列表中添加新类型
2. 在 `get_image_type_prompt()` 函数中添加对应的提示词

### 添加新的问题类型

在 `module1/qa_make.py` 中：
1. 在 `QUESTION_TYPES` 字典中添加映射
2. 在 `get_question_type_specific_requirements()` 函数中添加格式要求
3. 更新 argparse 的 choices

### 添加新的评估模型

在 `module2/config.py` 中的 `MODEL_CONFIG` 添加新模型配置。
