# 提示词拼接流程说明

本文档详细说明 module2 中提示词的拼接流程。

## 📋 整体流程

```
module1 输出数据
    ↓
model_evaluation.py::step1_call_models()
    ↓
_build_model_question() 构建问题文本
    ↓
answer_comparison.py::compare_three_models()
    ↓
get_model_answer() / get_model_answer_multi_round()
    ↓
models/model*.py::call_model*_api()
    ↓
PROMPT_TEMPLATE.format(question=question)
    ↓
最终发送给模型的提示词
```

## 🔄 单轮题提示词拼接

### 1. 问题构建阶段 (`model_evaluation.py::_build_model_question`)

输入：`item` 字典，包含：
- `question_type`: 题型（如 "四选单选"）
- `image_type`: 图片类型（如 "pure_text"）
- `question`: 问题文本（字符串）
- `options`: 选项（字典，可选）

输出：完整的问题文本，格式如下：
```
【题型】四选单选
【图片类型】pure_text
【问题】根据文本内容，以下哪项最能准确概括...
【选项】A: 选项A；B: 选项B；C: 选项C；D: 选项D
请根据上述信息给出唯一的最终答案，并用 \boxed{} 包裹该答案。
```

### 2. 模型调用阶段 (`models/model*.py::call_model*_api`)

输入：`question` 参数（来自 `_build_model_question` 的输出）

处理：
```python
prompt = PROMPT_TEMPLATE.format(question=question)
```

`PROMPT_TEMPLATE` 内容：
```
你是一个高级AI助手，擅长视觉和文本理解。请仔细分析以下问题并按照指定格式输出。

问题：{question}

回答要求：
1. 深入理解问题的本质和背景
2. 系统性地分析问题的各个层面
3. 清晰地展示你的推理过程和思考路径
4. 给出准确、完整的最终答案

⚠️ **重要：最终答案必须用 \boxed{} 格式括起来**

格式示例：
- 如果答案是数值：\boxed{42}
- 如果答案是百分比：\boxed{38%}
- 如果答案是文本：\boxed{这是答案}

注意：
- 推理过程可以包含任何你认为有用的思考步骤
- **最终答案必须用 \boxed{} 包裹，这是必须的格式要求**
- 不要使用Markdown代码块格式
- 输出语言应与问题语言保持一致
```

### 3. 最终提示词

```
你是一个高级AI助手，擅长视觉和文本理解。请仔细分析以下问题并按照指定格式输出。

问题：【题型】四选单选
【图片类型】pure_text
【问题】根据文本内容，以下哪项最能准确概括...
【选项】A: 选项A；B: 选项B；C: 选项C；D: 选项D
请根据上述信息给出唯一的最终答案，并用 \boxed{} 包裹该答案。

回答要求：
1. 深入理解问题的本质和背景
2. 系统性地分析问题的各个层面
3. 清晰地展示你的推理过程和思考路径
4. 给出准确、完整的最终答案

⚠️ **重要：最终答案必须用 \boxed{} 格式括起来**

格式示例：
- 如果答案是数值：\boxed{42}
- 如果答案是百分比：\boxed{38%}
- 如果答案是文本：\boxed{这是答案}

注意：
- 推理过程可以包含任何你认为有用的思考步骤
- **最终答案必须用 \boxed{} 包裹，这是必须的格式要求**
- 不要使用Markdown代码块格式
- 输出语言应与问题语言保持一致
```

## 🔄 多轮题提示词拼接

### 1. 问题构建阶段 (`model_evaluation.py::_build_model_question`)

输入：`item` 字典，包含：
- `question_type`: 题型（如 "多轮问答题"）
- `image_type`: 图片类型
- `question`: 问题字典（如 `{"round1": "...", "round2": "..."}`）
- `options`: 选项字典（可选）

输出：完整的多轮问题文本，格式如下：
```
【题型】多轮问答题
【图片类型】pure_text
【多轮问题】
round1：根据文本，2022年中国上榜世界500强的企业数量是多少？
round2：文中指出2021年中国世界500强企业营业收入占GDP比重为59.1%...
请分别回答每一轮的问题。
⚠️ **重要**：每一轮的答案必须单独用 \boxed{} 格式括起来。
格式示例：\boxed{round1答案} \boxed{round2答案}
```

### 2. 多轮调用阶段 (`answer_comparison.py::get_model_answer_multi_round`)

**第一轮（round1）：**

从完整问题文本中提取格式要求部分：
```
请分别回答每一轮的问题。
⚠️ **重要**：每一轮的答案必须单独用 \boxed{} 格式括起来。
格式示例：\boxed{round1答案} \boxed{round2答案}
```

构造 `round_question`：
```
round1：根据文本，2022年中国上榜世界500强的企业数量是多少？

请分别回答每一轮的问题。
⚠️ **重要**：每一轮的答案必须单独用 \boxed{} 格式括起来。
格式示例：\boxed{round1答案} \boxed{round2答案}
```

**后续轮次（round2, round3, ...）：**

构造 `round_question`（包含历史对话）：
```
下面是我们之前的对话历史（供你参考，不要重复回答）：
round1 问题：根据文本，2022年中国上榜世界500强的企业数量是多少？
round1 你的回答：145家，美国

现在是新的轮次 round2，请只回答本轮问题：
文中指出2021年中国世界500强企业营业收入占GDP比重为59.1%...
```

### 3. 模型调用阶段 (`models/model*.py::call_model*_api`)

每一轮都使用相同的 `PROMPT_TEMPLATE`：
```python
prompt = PROMPT_TEMPLATE.format(question=round_question)
```

### 4. 最终提示词（第一轮示例）

```
你是一个高级AI助手，擅长视觉和文本理解。请仔细分析以下问题并按照指定格式输出。

问题：round1：根据文本，2022年中国上榜世界500强的企业数量是多少？

请分别回答每一轮的问题。
⚠️ **重要**：每一轮的答案必须单独用 \boxed{} 格式括起来。
格式示例：\boxed{round1答案} \boxed{round2答案}

回答要求：
1. 深入理解问题的本质和背景
2. 系统性地分析问题的各个层面
3. 清晰地展示你的推理过程和思考路径
4. 给出准确、完整的最终答案

⚠️ **重要：最终答案必须用 \boxed{} 格式括起来**

格式示例：
- 如果答案是数值：\boxed{42}
- 如果答案是百分比：\boxed{38%}
- 如果答案是文本：\boxed{这是答案}

注意：
- 推理过程可以包含任何你认为有用的思考步骤
- **最终答案必须用 \boxed{} 包裹，这是必须的格式要求**
- 不要使用Markdown代码块格式
- 输出语言应与问题语言保持一致
```

## 📝 关键点总结

1. **单轮题**：问题文本由 `_build_model_question` 一次性构建，包含所有格式要求
2. **多轮题**：
   - `_build_model_question` 构建完整问题文本（包含格式要求），存储在 `qa_item["Q"]` 中
   - 实际调用时，从 `Q` 中提取格式要求，添加到每一轮的 `round_question` 中
   - 第一轮：`round_question = "round1：{问题}\n\n{格式要求}"`
   - 后续轮：`round_question = "历史对话\n\n现在是新的轮次 roundX：{问题}"`（格式要求已在第一轮给出，后续轮可省略）
3. **所有模型**（model1, model2, model3）使用相同的 `PROMPT_TEMPLATE`
4. **最终拼接**：`PROMPT_TEMPLATE.format(question=question)`，其中 `question` 是经过处理的问题文本

## 🔍 调试建议

如果模型输出格式不正确，检查：
1. `_build_model_question` 是否正确构建了格式要求
2. 多轮题时，格式要求是否正确传递到 `get_model_answer_multi_round`
3. `round_question` 的构造是否正确（特别是第一轮是否包含格式要求）
4. `PROMPT_TEMPLATE` 是否正确格式化

