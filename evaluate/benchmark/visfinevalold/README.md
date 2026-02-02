# VisFinEval TSV 转 JSONL 转换工具

## 功能说明

将 VisFinEval 数据集的 TSV 格式转换为 `qa_pipline12-7/evaluate_py` 评测框架需要的 JSONL 格式。

## 字段映射

| TSV 字段 | JSONL 字段 | 说明 |
|---------|-----------|------|
| `index` | `question_id` | 题目索引，用于标识题目 |
| `type` | `image_type` | 图片类型 |
| `round` | `round` | 轮次编号（多轮题目使用） |
| `answer` | `answer` | 标准答案 |
| `A, B, C, D` | `options` | 选项字典（格式：`{"A": "选项1", "B": "选项2", ...}`，三选题自动去掉D） |
| `image` | `image_path` | 图片路径（支持多图，逗号分隔） |
| `background_story` | - | 拼接到 `question` 前面，格式：`[背景信息] ...` |
| `information` | - | 拼接到 `question` 前面，格式：`[补充信息] ...` |
| `fintype` | `fintype` | 金融类型（保留作为额外信息） |
| `md_path` | `md_path` | Markdown 路径（如果有） |
| - | `scenario` | 场景分类（格式：`大文件夹名::TSV文件名`） |
| - | `question_type` | 题型（根据 `index` 前两位数字自动判断） |

## 输出文件

转换后的数据按三个大文件夹组织，每个文件夹下的所有 TSV 文件合并为一个 JSONL 文件：

1. `Financial_Analysis_and_Business_Decision.jsonl` (4,648 条)
2. `Financial_Knowledge_and_Data_Analysis.jsonl` (8,702 条)
3. `Financial_Risk_Control_and_Asset_Optimization.jsonl` (2,498 条)

## 使用方法

```bash
cd /home/zenglingfeng/qa_pipline12-7/evaluate/benchmark/visfineval
python3 convert_tsv_to_jsonl.py
```

## 输出格式示例

### 单轮题目

```json
{
  "question_id": "110001",
  "image_type": "lc",
  "question_type": "单选题",
  "scenario": "Financial Knowledge and Data Analysis::Financial_Data_Statistics",
  "image_path": "/home/zenglingfeng/VisFinEval/data/figure/lc/...",
  "question": "在2023年5月至2024年5月期间，房地产开发投资同比增速在哪个月份最低？\n\nA. 23-Jul\nB. 23-Dec\nC. 24-May",
  "options": {
    "A": "23-Jul",
    "B": "23-Dec",
    "C": "24-May"
  },
  "answer": "C",
  "fintype": "财务数据统计"
}
```

### 多轮题目

```json
{
  "question_id": "210201",
  "image_type": "fs",
  "question_type": "多轮单选题",
  "scenario": "Financial Knowledge and Data Analysis::Financial_Indicator_Assessment",
  "image_path": "/home/zenglingfeng/VisFinEval/data/figure/fs/...",
  "question": {
    "round1": "根据资产负债表，2023年流动资产总额是多少？\n\nA. 8727百万元\nB. 11542百万元\nC. 1.00元",
    "round2": "根据利润表，2023年的营业利润是多少？\n\nA. 1.00元\nB. 1.00元\nC. 1052百万元"
  },
  "answer": {
    "round1": "A",
    "round2": "C"
  },
  "options": {
    "round1": {
      "A": "8727百万元",
      "B": "11542百万元",
      "C": "1.00元"
    },
    "round2": {
      "A": "1.00元",
      "B": "1.00元",
      "C": "1052百万元"
    }
  }
}
```

## 处理逻辑

1. **多轮题目处理**：按 `index` 分组，按 `round` 排序，转换为多轮格式
2. **选项处理**：自动识别三选题（D为空）和四选题，转换为字典格式 `{"A": "...", "B": "...", ...}`
3. **问题拼接**：背景信息和补充信息自动拼接到问题前面
4. **场景分类**：`scenario` 字段包含大文件夹名和 TSV 文件名，用 `::` 分隔
5. **题型判断**：根据 `index` 的前两位数字自动判断题型并设置 `question_type` 字段

## 题型映射

根据 `index` 前两位数字判断题型：

| 前缀 | 题型 | 说明 |
|------|------|------|
| 11, 12, 15, 16, 31, 32, 33 | 单选题 | 单项选择 |
| 13 | 多选题 | 多项选择 |
| 14 | 判断题 | 判断对错 |
| 21, 22, 23 | 多轮单选题 | 多轮单项选择 |
| 34 | 问答题 | 问答 |

## 统计信息

- 总题目数：15,848 条
- 单轮题目：14,464 条
- 多轮题目：1,384 条

