import os
import json
import base64
import time
import threading
import re
import random
import concurrent.futures
import argparse
import signal
import sys
from openai import OpenAI
try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False
    print("⚠️ 提示: 安装 tqdm 可以获得更好的进度显示: pip install tqdm")

# ==============================================================================
# 🌍 全局配置容器
# ==============================================================================
GLOBAL_CONFIG = {
    "api_base": "",
    "api_key": "",
    "model_name": "",
    # 如果不设置，则使用模型默认温度
    "temperature": None,
    "max_tokens": 8192,
    "batch_size": 10,
    "max_workers": 4,
    "questions_per_image": 1,
    "enable_thinking": False,  # 是否启用思考模式（启用后会提取 reasoning_content）
    "rounds": 3,               # 多轮对话的轮数（仅用于多轮对话题型）
    "request_timeout": 1000.0,   # 单次请求超时时间（秒）
    "max_retries": 3,          # 请求最大重试次数
    "retry_sleep": 1.0,        # 失败后的基础重试间隔（秒）
    "log_mode": "simple",      # 日志模式: "simple"(简化) 或 "detailed"(详细)
    "include_process": False    # 是否生成 qa_make_process 字段（推理过程）
}

# ==============================================================================
# ⚙️ 全局变量与锁
# ==============================================================================
client = None
file_lock = threading.Lock()
buffer_lock = threading.Lock()
result_buffer = [] 
stats = {
    "success": 0,           # 成功生成问题的数量
    "failed": 0,            # 失败的图片数量
    "images_processed": 0,  # 已处理的图片数量
    "questions_generated": 0,  # 已生成的问题数量
    "images_success": 0,    # 成功处理的图片数量（至少生成1个问题）
    "images_failed": 0      # 完全失败的图片数量（0个问题）
}
OUTPUT_PATH = "" 
OUTPUT_FORMAT = "jsonl"  # 输出格式：json 或 jsonl（根据文件扩展名自动判断）
CURRENT_IMAGE_TYPE = ""
CURRENT_QUESTION_TYPE = ""
FIRST_ITEM_PROCESSED = False  # 用于标记是否已处理第一道题（用于调试输出）
progress_bar = None  # 进度条对象
progress_lock = threading.Lock()  # 进度条更新锁
LOG_FILE = None  # 日志文件对象
log_lock = threading.Lock()  # 日志写入锁
shutdown_event = threading.Event()  # 用于标记是否需要优雅关闭

# 日志优化：计数器，控制完整显示的日志数量
_log_full_display_count = 0  # 完整显示的日志数量
_LOG_FULL_DISPLAY_LIMIT = 3  # 前N个完整显示，之后显示省略版

# ==============================================================================
# 📝 问题类型定义
# ==============================================================================
# 🔧 扩展说明：要添加新问题类型，只需在这里添加映射关系
QUESTION_TYPES = {
    "single_choice": "四选单选",      # 单选题
    "multiple_choice": "四选多选",    # 多选题
    "true_false": "判断题",           # 判断题
    "essay": "问答题",                # 问答题
    "multi_round_single_choice": "多轮单选题",  # 多轮单选题
    "multi_round_essay": "多轮问答题"  # 多轮问答题
    # 添加新问题类型示例：
    # "fill_blank": "填空题",
    # "matching": "匹配题",
}

# ==============================================================================
# 📝 图片类型定义
# ==============================================================================
# 🔧 扩展说明：要添加新图片类型，只需在这里添加
IMAGE_TYPES = ["pure_image", "pure_text", "mixed", "splice", "stacked", "all"]
# "all" 表示处理所有类型的图片，不进行筛选
# 添加新图片类型示例：
# IMAGE_TYPES = ["pure_image", "pure_text", "mixed", "splice", "all", "video_frame", "3d_model"]

# ==============================================================================
# 📝 提示词模板系统 (可扩展设计)
# ==============================================================================

def get_image_type_prompt(image_type: str, question_type_name_cn: str, rounds: int = 1, include_process: bool = True) -> str:
    """
    获取特定图片类型的完整出题提示词
    🔧 扩展说明：添加新图片类型时，只需在这里添加对应的完整出题逻辑
    注意：每种图片类型都有独立的出题逻辑，不共享通用部分
    rounds: 多轮对话的轮数（仅用于多轮对话题型）
    """
    # 判断是否为多轮对话题型
    is_multi_round = "多轮" in question_type_name_cn
    rounds_text = f"{rounds}轮" if is_multi_round else ""
    
    prompts = {
        "pure_image": f"""
你是一名专业的金融推理题目构建专家，擅长根据图像内容生成高质量的困难金融多模态 VQA 问题。

给你的一张图像来自证券/研究机构的正式金融研报，内容可能是：
- **统计图表**：折线图、柱状图、饼图、雷达图、散点图等；
- **报表/表格**：财务报表、盈利预测表、估值表、股权结构表、数据汇总表等；
- 多幅子图或图表+表格的组合。

你的任务：  
**在完全依赖该图像内容的前提下，生成一道题目 + 标准答案，用于评估大模型在金融研报图像“精准定位 + 理解 + 推理”方面的能力。**
题型为【{question_type_name_cn}】。

【全局数值使用总规则】

- 所有需要使用具体数字进行计算的步骤，**只能**使用图像中以文字形式写出的数字，例如：
  - 表格或列表中的数字；
  - 标在柱子、折线数据点、扇区等旁边的数字标签或百分比；
  - 图内文字说明、标注框、脚注中的数字。
- **坐标轴上的刻度数字、网格线位置以及柱高/线高本身都不算可用数字，不允许据此读出或推断具体数值。**
  - 例如：不得说“该点在 0.6 刻度线上，所以数值为 0.6”，也不得用“介于 0.4 和 0.6 之间所以约等于 0.5”等方式获取数字。
- 若某张图像没有任何以文字形式写出的具体数字（例如只有折线走势或柱子形状），则：
  - 只能设计**趋势/相对高低/正负方向/排序**等定性比较问题；
  - **严禁**设计需要具体数值、差值、增速、百分比等计算题。

1. **题目难度需达到资深金融分析师/研究员水平**
   至少同时使用 3 个及以上不同的数据点 / 指标 / 维度（例如：两个年份 + 两个指标 + 一个比例 / 分类）；
   至少涉及 2 类信息来源，例如“折线图趋势 + 图例/颜色 + 图内文字注释/脚注”或“表格 + 图表”；
   至少包含 2 种不同类型的运算或逻辑：
   - 若图中存在明确文字数字，可使用“同比/环比 + 比率比较”“加权平均 + 增长率”“解方程 + 排序”等数值推理；
   - 若图中没有可用数字，则使用“不同时间区间的趋势模式比较 + 多条曲线/多根柱子的相对排序”等纯定性推理。
   若图像中存在多个子图或表格，优先且尽量要求题目同时使用至少两个子图/表格的信息：
   最终答案必须依赖这种跨子图的对应关系，不能只在一个子图内就能解出。
   若图像确实只有一个子图或单表格，需要使用该图内部的多个维度（如时间 + 地区 + 指标/项目）以保证复杂度。

2. 你可以设计的问题类型包括但不限于：
   - 财务指标推理（需通过计算或多指标逻辑组合才能得到结论，而不是直接读数）
   - 图表趋势分析与推断（必须通过二阶变化、速度变化、区间比较等间接方法得出唯一答案）
   - 结构化图形推理（股权结构、资产结构、业务构成，需要多层穿透或占比计算）
   - 多实体关系推断（至少 3 个以上实体的比较 / 排序 / 贡献分解）
   - 跨指标链式推理（A 指标变化 → 影响 B 指标 → 再与 C 指标比较后得出结论）
   - 跨子图综合分析（至少 2 个子图之间建立对应关系，如时间、行业、地区等维度）
   - 禁止设计：依赖单一显眼特征即可作答的问题（如“哪条线最高”“哪根柱子最长”）；只用到一个数字或一个类别的信息的问题。
   

3. **图形类型的强制要求**
    图中若出现以下图形则需遵守对应原则：
    A. 折线图
    若图中有折线图，且你选择基于折线图出题，则：
    题目必须围绕**趋势形态和相对比较**，而不是具体数值或精确增幅。只允许的操作包括（至少满足其中两项）：
   - 判断某一指标在不同时间区间内是“持续上升 / 持续下降 / 先升后降 / 先降后升 / 大致持平”等；
   - 比较同一条折线在两个不同区间内的**走势特征**，例如哪一段上升更明显、哪一段波动更剧烈、哪一段更平稳（基于折线形状和波动次数，而不是具体数值差）；
   - 比较两条或多条折线在同一时间区间内的**相对表现**，例如：哪条线更早出现拐点、哪条线更早开始下行、哪条线在大部分时间里处于更高水平；
   - 利用折线图中的事件标注/阴影区间作为边界，只在这些区间内比较“趋势方向”“是否出现拐点”“波动是否放大/收敛”等。

    B. 柱状图或堆叠柱状图
    若图中有柱状图，且你选择基于柱状图出题，则：
    题目必须围绕**相对高低、排序、变化方向**等定性关系，而不是具体数值或精确差值。只允许的操作包括（至少满足其中两项）：
   - 比较同一时间点下不同项目的**相对高低或排名**，例如“哪一项贡献最大/最小”“哪些项目明显高于/低于全部样本的平均水平”（仅基于柱子长短的明显差异，而非数值差）；
   - 比较同一项目在不同时间点或不同地区的**变化方向**，例如“是上升、下降还是基本持平”“哪一段变化更明显”，只根据柱子变长/变短来判断；
   - 判断某类柱子是**正值还是负值**，或是否明显“由正转负 / 由负转正”；
   - 对堆叠柱，比较不同组成部分的**相对占比和变化方向**，但不要求具体百分比。

    C. 表格
    若图中有表格，并被用作出题依据，则必须：
   - 至少使用 **3 列或 3 行** 的信息，而不是只读某一行/某一列的单点数值；
   - 利用行间/列间关系构造显式或隐含的方程（如“利用率 = 数量 / 总量”“ROE = 净利润 / 净资产”）来反推某个隐藏指标或绝对值；
   - 进行多指标的**加权合成或交叉比较**，不得只做一次简单加减法；
   - 在条件允许时，优先设计“表格 + 图表”联合推理题，例如：先用表格算出某指标，再到图表中比较其相对表现。

4. **问题必须属于金融领域的实际子任务之一**，如：
   - 公司金融：财务报表分析、利润结构、资产负债表项目推算；
   - 行业分析：行业或板块指标比较、市场份额变化、竞争格局；
   - 股票估值：估值指标计算、财务比率推导；
   - 风险管理：波动率、风险暴露、风险收益比等比较；
   - 资产管理：资产配置、投资组合表现分析；
   - 市场分析：宏观经济图表（通胀、工业、地产、商品、利率等）、市场成交量与价格联动；
   - 财务指标计算：ROE、ROA、毛利率、净利率等指标推算；
   - 股权结构分析：持股比例、控制权穿透、实际控制人识别。

5. **所有问题必须满足**：
   - 答案唯一、客观、可验证（不能有歧义或多种解释）
   - 必须严格依赖图像中的信息（不能依赖图外知识或假设）
   - 题干不得直接给出图片内已有的结构化数据或结论
   - 不允许主观类问题（如"你怎么看""是否合理"）
   - 不允许开放式回答（如"列出可能的原因""可能有哪些影响"） 

6. **难度要求：结合但不限于以下要求**：
   - 涉及跨年度、跨季度、跨区域的趋势比较
   - 同时使用图表数值 + 图例解释 + 文字说明
   - 结构占比变化推断（如"哪部分贡献最大""结构如何变化"）
   - 使用图中多个图块（如主图 + 子图 + 表格）综合推断

7. - 计算题仅在图像中**存在明确的文字数字（尤其是表格或数据标签）**时才允许设计；
    对于仅包含折线图、柱状图、雷达图等、而没有任何文字数字的图片，**一律不得设计计算题，只能设计定性比较题**。
    在允许设计计算题的前提下，计算题不得只包括加减乘除，还需包括但不限于如下复杂操作：
    有限差分、二阶差分；
    对数变换、对数差；
    CAGR/年化增长；
    解析型拟合（线性/指数）；
    解线性方程组；
    加权贡献分解；
    标准化归一化。

8. **关于答案格式的要求（重要）**：
   - 若答案为明确的**数值型答案**（如百分比、金额、增长率、比率等），则为计算题，不需要设置选项
   - 若答案**不是单一数值**，但依然客观唯一（如"增长最快的是某行业""占比最高的是某地区"），则必须设计为选择题，需提供合理的干扰选项
   - 严禁出现明显错误或离谱选项，例如“其他”“无法判断”“随意的非金融名词”等。
   - 注意：题型（{question_type_name_cn}）已指定，需要严格按照题型要求设计题目

{"9. **思维链要求**：\n   必须在 qa_make_process 字段中详细记录解题的完整推理链条，包括：\n   - 从文本的哪些位置（段落、句子）获取了哪些信息\n   - 如何理解这些信息（包括专业术语的解释）\n   - 如何将多个信息点组合起来进行推理\n   - 每一步的逻辑判断或计算过程\n   - 最终如何得出答案\n\n" if include_process else ""}


{"10.**多轮对话要求**：需要设计" + rounds_text + "轮对话，每轮都有独立的问题和答案，形成完整的对话流程。每轮问题都应遵循上述所有要求，且各轮之间应形成逻辑递进或关联（如：第1轮读取数据 → 第2轮计算指标 → 第3轮综合判断）。" if is_multi_round else ""}
""",
        "pure_text": f"""
你是一名**【高级金融定量分析师兼对抗性设计专家】**，专长是从复杂的金融研报纯文字内容中，设计出**具有极强 AI 迷惑性、需要多维度高阶推理**的 VQA 问题。

请基于提供的金融研报文字图像（纯文本内容），生成一道【{question_type_name_cn}】，用于评估大模型在**金融知识深度理解、多步复杂逻辑推理及抗干扰分析**方面的极限能力。

---

### 一、 设计哲学：AI 对抗性与宁缺毋滥

1.  **【核心目标：AI 盲区狙击】**
    生成的题目必须瞄准当前大型语言模型的常见弱点：**关键词匹配、数据混淆和浅层因果推导**。确保题目需要**人类级别的细读**才能锁定答案。

2.  **【质量优先原则】**
    你只需要为每张图片构造**少量但质量极高、区分度极强**的问题。如果文本信息不足以支撑“地狱难度”的题目，宁可放弃生成。

---

### 二、 逻辑难度强化约束（14项精细化升级）

#### 1. 强制性“多维信息整合” (Multi-Hop Integration)

* **执行标准**：答案必须同时依赖 **3 处及以上**不同句子或段落的信息，且这些信息在原文中位置显著分散。
* **【硬性约束：三点定位】**：不得只基于单一句子或相邻段落即可作答。
* **考察点**：**结构化信息重组**（将分散在文本中的数据和逻辑关系进行三维拼图）。

#### 2. 金融实务与跨界逻辑

* **要求**：问题必须聚焦于**金融分析的实际认知链条**，例如：
    * **业绩驱动力剖析**：识别影响业绩的**核心因素**，并推断其**作用的持续性**（而非简单列举）。
    * **竞争格局动态分析**：结合市场份额、技术路线和政策导向，推导**竞争地位的潜在变化**。
    * **投资逻辑的矛盾检验**：用风险因素和盈利质量去**反向验证**研报的投资建议是否过度乐观。

#### 3. 答案的客观性与定位性

* **硬性要求**：答案必须是**唯一、客观、可验证**的。
* **严禁**：主观臆测、开放式回答，以及任何需要外部常识才能回答的问题。
* **题干设计**：不允许直接泄露任何关键信息或结论，必须通过**提供定位线索**来引导模型。

#### 4. 复杂数值推理与经济含义判断

* **数值复杂度**：禁止单步四则运算。必须设计需要**两步及以上数值推理**的问题。
* **【强制要求】**：计算过程必须包含**“数值推导”**和**“经济含义判断”**两个层次。
    * *例如*：先算出某费用项的同比增速，再结合营收增速，判断该项费用是“刚性支出”还是“规模效应优化”的体现。
* **比例约束**：**至少 40% 的题目**需包含复杂数值计算，以确保题目难度。

#### 5. 多实体、多维度比较的深度排序

* **维度要求**：比较题必须同时考虑**至少三个以上**维度的信息（如：增速、利润率、波动性、政策敏感度）。
* **非直接排序**：答案不能通过单一指标（如“谁的增速最高”）直接得出，需要**综合权衡**。
* *示例*：结合 A 业务的“增长弹性”和 B 业务的“现金流稳定性”，判断哪项是公司“长期价值的压舱石”。

#### 6. 引入“逻辑陷阱”与“干扰信息”

* **干扰设计**：优先选取周围存在**大量相似干扰信息**（相似时间点、相近数值、相似概念）的文本片段来设计题目。
* **避坑要求**：题目应刻意避免选择“唯一出现的数字/实体”，强制模型必须**真正理解上下文逻辑**，而非关键词匹配。

#### 7. 考察“隐含条件 / 反向信息”的辨析

* **挖掘潜台词**：鼓励构造需要识别**隐含条件、反向约束**或**“未被覆盖情形”**的题目。
* **否定句理解**：要求考察模型对**否定句、例外条款、假设前提**（如“除非...否则不...”）的精确理解。

#### 8. 语气、不确定性与风险表述的精确理解

* **语义微操**：设计题目考察模型对结论**置信度、时间维度和风险提示强度**的理解。
    * *示例*：根据研报措辞，判断某项观点是“管理层的战略意图”还是“分析师的审慎假设”。
* **风险穿透**：要求判断某项风险是“结构性长期风险”（如技术淘汰）还是“短期扰动”（如季节性影响）。

#### 9. 强化“时间维度与因果链条”的复杂推演

* **阶段性切换**：鼓励设计需要明确分辨**不同时间点、不同阶段**的题目，推理驱动因素是否发生**阶段性切换**。
* **完整链条**：至少部分题目需要构造完整的**“政策/事件 → 业务指标变化 → 财务结果/估值影响”**三段式因果链条，并要求模型在答案中体现这一链条。

#### 10. “投资逻辑 / 估值逻辑”的综合性挑战

* **综合约束**：至少设计 **1 道综合题**，需要同时利用：**业务/行业描述**、**财务指标/盈利质量**、以及**风险因素**三类信息。
* **深度推理**：要求根据正文推理**“为什么是这个建议，而不是更激进/更保守”**，而非简单询问投资建议。

#### 11. 严禁的行为（再次强调）
* 严禁编造信息、引用图外知识、题干泄露答案或设计依赖常识的问题。


{"12. **多轮对话要求**：需要设计" + rounds_text + "轮对话，每轮都有独立的问题和答案，形成完整的对话流程。每轮问题都应遵循上述所有要求，且各轮之间应形成逻辑递进或关联（如：第1轮信息提取 → 第2轮逻辑推理 → 第3轮综合判断）。" if is_multi_round else ""}
{"**多轮对话递进复杂度要求**（仅适用于多轮对话题型）：" if is_multi_round else ""}
{"- 第 1 轮问题应侧重关键信息提取与基础理解；" if is_multi_round else ""}
{"- 第 2 轮基于第 1 轮的答案，进一步进行数值推理、比较或因果分析；" if is_multi_round else ""}
{"- 第 3 轮及以后在前两轮信息之上，进行更高层次的综合判断，例如投资逻辑的自洽性、风险收益权衡等。" if is_multi_round else ""}
{"- 后续轮次的问题设计时，应在题干中隐式依赖前一轮的结论，但答案仍能通过原始文本 + 前轮结论唯一确定，避免出现多种合理解读。" if is_multi_round else ""}
{"- 多轮问题之间尽量避免重复考察完全相同的信息点，每一轮都应聚焦于新的推理角度（例如从'收入驱动'转向'成本与利润率''风险与政策'等）。" if is_multi_round else ""}

---
{"### 三、 思维链（QA Process）高标准规范\n\n你必须在 `qa_make_process` 字段中详细记录解题的**完整、对抗性推理链条**。\n\n* **步骤数量**：至少包含 **4 步以上**的推理标签。\n* **精细化标注**：除了描述推理步骤外，必须显式标注每一步所依赖的**文本位置**，并精确注明该步的类型：\n    * 信息抽取（Extraction）\n    * 数值计算（Calculation）\n    * 比较排序（Comparison）\n    * 因果推理（Causal reasoning）\n    * 语义/语气判断（Semantic / Modality）\n    * 反向/隐含推理（Inverse/Implicit）\n\n* **【关键新增】**：推理链中必须有一步明确指出：**\"本步骤如何规避了 XX 干扰项（例如：2022 年数据）或 XX 逻辑陷阱（例如：毛利率与净利率的口径混淆）。\"**\n\n" if include_process else ""}
---
""",
        "mixed": f"""
你是一名顶级的金融多模态高难度 VQA 题目构建专家，擅长从复杂的"图表+文字说明"类金融图像中，设计需要多层逻辑链条的专业级分析题。

请基于给定的金融图像（可能包含折线图、柱状图、饼图、同比/环比数据、百分比结构、表格、说明文字、指标定义、图例、注释等多种元素），生成一道【{question_type_name_cn}】。题目难度需显著高于一般金融研究员水平，必须依赖图中多个信息块的交叉使用（图表 + 文字说明 + 注释 + 图例）。

**【任务要求】**

1. **题目难度需达到金融分析师/研究员水平**
   必须生成需要多步推理的金融推理问题，问题的答案只能依赖图像中的内容得到,推理。题目类型可以包括但不限于：
   - 财务指标推理（基于图中数据进行计算或逻辑推断）
   - 图表趋势分析与推断（识别拐点、加速/减速、周期性等）
   - 结构化图形推理（如股权结构、资产结构、业务构成等）
   - 多实体关系推断（比较、排序、关联分析等）
   - 比较类问题（增长最快、占比最高、结构变化、相对表现等）
   - 经济或业务含义推断（基于图中客观信息得出结论）
   - 跨图表综合分析（多项指标之间的链式推断，如 A→B→C）
2. **图形类型的强制要求**
    图中若出现以下图形则需遵守对应原则：
    A. 折线图
    -只能引入明确图片或文字中有标注的数据，不得根据折线图和坐标轴观察出近似数据，若没有明确数据则禁止出相应数值计算类型题目。
    问题参考：
    -二阶差分/离散加速度判断拐点；
    -线性/指数拟合并内插或短期外推；
    -对数收益率、链式指数或复合增长；
    -使用折线图中的注释/事件窗口作为运算约束。
    B. 柱状图或堆叠柱状图
    -只能引入明确图片或文字中有标注的数据，不得根据折线图和坐标轴观察出近似数据，若没有明确数据则禁止出相应数值计算类型题目。
    问题参考：
    -结构变化归因分解（权重 * 变动）；
    -跨期标准化（如按基期或人均）；
    -度量统一转换（百分比 ↔ 绝对值）。
    C. 表格
    问题参考：
    -利用列间/行间约束构造方程求解隐藏指标；
    -多指标标准化或加权合成；
    -利用率类指标反推绝对数。
3. **所有问题必须满足**：
   - 答案唯一、客观、可验证（不能有歧义或多种解释）
   - 必须严格依赖图像中的信息（不能依赖图外知识或假设）
   - 题干不得直接给出图片内已有的结构化数据或结论
   - 不允许主观类问题（如"你怎么看""是否合理"）
   - 不允许开放式回答（如"列出可能的原因""可能有哪些影响"）
   - 选择题必须包含正确选项，对于计算类型可以先算出答案后把答案作为选项之一 
   - 答案最好由图表和文字两部分信息共同推理得出
4. **难度要求：结合但不限于以下要求**：
   - 涉及跨年度、跨季度、跨区域的趋势比较
   - 同时使用图表数值 + 图例解释 + 文字说明
   - 多指标之间的链式推理（A→B→C，需要至少 2-3 步推理）
   - 结构占比变化推断（如"哪部分贡献最大""结构如何变化"）
   - 从同比 + 环比的叠加信息得出判断
   - 使用图中多个图块（如主图 + 子图 + 表格）综合推断
   - 计算题不得只包括加减乘除，还需包括但不限于如下复杂操作：
    有限差分、二阶差分；
    对数变换、对数差；
    CAGR/年化增长；
    解析型拟合（线性/指数）；
    解线性方程组；
    加权贡献分解；
    标准化归一化。

5. **关于答案格式的要求（重要）**：
   - 注意：题型（{question_type_name_cn}）已指定，需要严格按照题型要求设计题目


6. **严禁的行为**：
   - 不得在题干中直接泄露图中的关键数据或结论
   - 不得设计依赖外部知识或背景才能回答的问题
   - 不得设计答案模糊或有多种可能解释的问题
   - 不得设计主观性较强的推断预测问题，答案必须要有明确依据,例如折线图不得出估算数值、预测趋势等问题。


{("7. **思维链要求**：\n   必须在 qa_make_process 字段中详细记录解题的完整推理链条，包括：\n   - 明确说明针对的是哪张图片（如\"基于上图\"或\"基于关于XX的图表\"）\n   - 从该图片的哪些位置获取了哪些信息\n   - 如何将这些信息组合起来进行推理\n   - 每一步的计算或逻辑判断过程\n   - 最终如何得出答案\n\n" if include_process else "")}

{"8. **多轮对话要求**：需要设计" + rounds_text + "轮对话，每轮都有独立的问题和答案，形成完整的对话流程。每轮问题都应遵循上述所有要求，且各轮之间应形成逻辑递进或关联（如：第1轮识别数据 → 第2轮计算指标 → 第3轮综合判断）。所有轮次的问题都必须针对同一张图片。" if is_multi_round else ""}
""",
        "splice": f"""
你是一名**地狱级难度**的金融多模态 VQA 题目构建专家。
你的核心任务是：在视觉环境极度恶劣（严重噪声、几何形变、遮挡）且信息碎片化的场景下，构建**顶级对冲基金面试级别**的逻辑推理题。

---

## 【输入图像与场景定义】
你面对的是一张**极高难度的金融拼接图像**，具有以下特征：
1.  **复杂拼接布局**：图像由多张文档拼接而成，布局可能是：
    - 基础拼接：左右拼接、上下拼接。
    - 复杂拼接：**品字形拼接**（上方主图+下两子图，或反之）、田字形拼接。
2.  **严重视觉干扰**（Hard Sample）：
    - **几何变换**：图像存在非线性倾斜、波浪状弯曲、折痕（导致坐标轴非线性扭曲）。
    - **材质损伤**：表面有咖啡渍、透墨（背面文字干扰）、纸张纹理严重。
    - **光学干扰**：局部阴影、强反光（光斑覆盖关键数据）、动态模糊。
    - **恶意遮挡**：关键区域有手指按压、笔杆遮挡、大面积水印覆盖。

---

## 1. 区域锁定与抗扰定位（最高优先级）
你必须在思维链（qa_make_process）的开头，先进行**布局解析与抗扰评估**。

### 步骤 A：锁定子区域
根据识别到的拼接布局，明确选择并锁定一个独立区域（例如：“左上子图”）。
**注意**：
- 必须优先选择**视觉陷阱最多**但逻辑尚可推断的区域，以增加题目挑战性。
- 如果某区域关键数据被彻底破坏（如墨渍覆盖核心数值），请放弃该区域，选择另一个。
- **一旦选定，后续所有推理严格限制在此区域内，视其余部分为透明。**

### 步骤 B：模拟“无方位”题干
最终输出的 `Question` 和 `Answer` 中，**绝对禁止**出现方位词（如“左边”、“下方”、“品字形上部”）。
*题目必须模拟用户只能看到被裁剪出来的这一张图的视角。*

---

## 2. 图像类型自适应出题规则（地狱难度版）
你需要识别所选子图的类型，并应用对应的**高阶抗干扰出题策略**：

### ① 若锁定区域为：折线图（趋势/形态类）
**【核心铁律】：禁止读取绝对数值，必须进行“二阶形态分析”。**
由于透视变形，读取网格值会产生幻觉。
- ❌ **绝对禁止**：简单的涨跌判断、具体数值读取（如“收盘价是多少”）。
- ✅ **必须生成（考察高阶视觉认知）**：
    - **波动率分析**：尽管图片倾斜，判断波动率是“扩张”还是“收敛”（如喇叭口形态）。
    - **相对强度逻辑**：对比两条曲线的动量（如“虽然A曲线位置更低，但其反弹斜率是否显著高于B曲线？”）。
    - **形态陷阱识别**：识别并排除由“折痕”或“污渍”造成的伪趋势（假突破）。

### ② 若锁定区域为：柱状图/饼图/复杂表格
**【核心铁律】：多重逻辑嵌套与缺失值推断。**
- **计算链要求**：必须包含 **≥ 5 步** 的非线性推理（例如：结合图例排除干扰项 → 利用总量反推被遮挡项 → 计算占比 → 与隐含阈值比较）。
- **抗遮挡/噪声策略**：
    - 针对被手指/异物遮挡的数据，必须利用“会计恒等式”或“归一化逻辑”（Total = 100%）反推隐形数据。
    - 引入**条件判断**：题目应包含“如果...则...”的逻辑（例如：“假设被遮挡的Q3数据等于Q1与Q2的均值，求全年的增长率”）。

### ③ 若锁定区域为：图文混合（图表 + 注释 + 图例）
**【核心铁律】：多模态互证与冲突消解。**
- **高难度互证**：图表视觉信息可能受损（如模糊），强迫模型利用微小的文字注释（Footnote）来修正对图表的理解。
- **陷阱设计**：寻找图表视觉趋势与文字标题看似矛盾的点（例如标题是“成本下降”，图表是“毛利上升”），要求解释其内在一致性。

### ④ 若锁定区域为：纯文字/研报截图
**【核心铁律】：语义深层重组，拒绝OCR搬运。**
- 针对揉皱/弯曲文本，考察**隐含逻辑**（Implied Logic）。
- **提问方式**：不要问“提到了什么”，要问“根据段落逻辑，作者暗示的核心风险是什么？”或“这段论述与标准会计准则的冲突点在哪里？”。
- **答案限制**：核心结论，**长度 < 20 字**。

{"---\n\n## 3. 思维链（qa_make_process）执行标准\n你的内部推理过程必须包含以下五个明确的标签步骤，且必须体现**博弈思维**：\n\n1.  **【布局与选区】**：声明识别到的拼接结构，并锁定一个最具挑战性的区域。\n2.  **【噪点与陷阱评估】**：明确指出该区域的视觉干扰（如：\"右侧y轴被光斑覆盖，且折痕导致Q3柱状图视觉高度失真\"）。\n3.  **【抗扰与清洗策略】**：说明如何建立\"逻辑防火墙\"（如：\"放弃视觉直读，转而通过累计值减去可见值来反推遮挡数据\"）。\n4.  **【深度推理路径】**：展示完整的逻辑链条，必须包含至少一次\"修正\"或\"反转\"过程（如：初步看是上涨 -> 结合通胀注释修正为实际下降）。\n5.  **【独立性自检】**：确认答案未利用锁定区域以外的信息，且逻辑闭环。\n\n---\n\n" if include_process else ""}
## 4. 难度与质量控制
- **题目难度**：**竞赛级/专家级**。题目必须包含至少一个逻辑转折点。
- **唯一性**：尽管推理过程极度复杂，最终答案必须是收敛的、客观唯一的。
- **容错性**：题目设计应容忍轻微的视觉误差（关注相对关系而非绝对精度），但对逻辑错误零容忍。

{"7. **多轮对话要求**：需要设计" + rounds_text + "轮对话，每轮都有独立的问题和答案，形成完整的对话流程。每轮问题都应遵循上述所有要求，难度呈螺旋上升趋势（如：第1轮识别抗扰特征 → 第2轮进行条件推理 → 第3轮综合决策）。所有轮次的问题都必须针对同一张图片。" if is_multi_round else ""}
""",
        "stacked": f"""
    你是一名专注金融研报图表的高级出题专家，需要生成一道**超高难度**题目，考察模型在**两张堆叠金融图片**（stacked）上的精准定位、跨图关联与复杂推理能力。图片可能存在弯曲、透视、污渍、折痕等真实扰动。

题型：{question_type_name_cn}；

总体目标：题目必须引导模型在两张图/表之间进行信息对齐、跨图映射和链式推理，答案唯一、客观、可核验；必须在题干中明确指向涉及的子图/表（如“上层折线图”“下层表格”），并在答案或推理链中点名对应位置/标签。

严格规则（包含折线图禁读数）：  
1) 难度强度：  
   - 至少 3-4 个独立信息点，且至少 2 个来自不同子图/表格；  
   - 推理链 ≥3 步，优先跨子图/跨时间/跨指标的多跳推理；  
   - 必须体现“定位→比对→推断”全过程，避免直接抄读。  
2) 数值/文本引用：  
   - 只能使用图中明文出现的数字、百分比或表格文字；严禁用坐标刻度、柱高/线高、颜色深浅等视觉估读或外推；  
   - 若数字存在单位/币种/区间，需在题干中明确引用并保持一致；禁止自创新单位或补全缺失小数。  
3) 折线图限定： 如果你识别到图片是折线图，则需要严格遵守以下规则 
   - 仅允许趋势、相对高低、拐点顺序、领先/滞后关系等定性判断；  
   - 禁止读取或估算具体数值、差值、增速；若无明文数字，只能做定性比较，不得出计算题。  
4) 无明文数字场景：仅可做趋势、高低、正负、排序、占比对比等定性问法，禁止任何计算或数值推断。  
5) 题型区分与独特需求：  
   - 单选：A/B/C/D 仅一真，干扰项需在跨图对齐点上制造“时间偏移/指标错配/子图位置混淆/数值单位错置”；题干必须指明两个子图的具体片段与时间/指标；答案需由至少两处信息共同锁定，不得由单一信息点直接得出。  
   - 多选：至少两真，正确选项需“联合满足两图条件 + 逻辑链完整”；错误项要么缺少其中一图的必要条件，要么只满足单图，或链条断裂；需避免“全对/全错”结构，并防止通过排他法轻易猜出。  
   - 判断：answer 为 true/false，陈述里必须显式包含“跨图对应元素 + 时间/地区/指标 + 子图位置”三要素，可直接在图中逐条核验；应设计一处易混淆的近似表述以测试精确比对能力。  
   - 问答：答案为简洁实体/结论/短语，题干需点明所用的两个信息块及推理链关键跳点（如“上层折线图的峰值年份 + 下层表格的同比列”）；答案必须唯一、可在两图交叉验证。  
6) 高阶考点（至少选择 2 项组合）：  
   - 跨年度/季度/地区趋势对比或交叉验证；  
   - 结构占比/贡献度的变化与排序；  
   - 多指标链式推理（A→B→C，需显式说明链条）；  
   - 跨子图时间/行业/地区的对应与映射；  
   - 表格 + 图表联合推理，要求明确子图来源与引用字段。  
7) 题干表达：需在题干中点明使用了哪些子图/表格片段（如“上层折线图”“下层柱状图”“右侧表格”），并确保描述与图中实体一致，不得创造缺失的标签或时间轴。  
8) 失败处理：若在给定图片无法构造满足全部规则的题目，返回 `qa_make_status = "NO_VALID_QUESTION"`。

{"思维链：在 qa_make_process 中按“定位信息→读取内容→比对/运算→排除干扰→得出结论”细分不少于 5 步，逐步标注查看的区域/文字数字与对应推理动作。" if include_process else ""}

{"**多轮对话要求**：需要设计" + rounds_text + "轮对话，每轮都有独立的问题和答案，形成完整的对话流程。每轮问题都应遵循上述所有要求，难度呈螺旋上升趋势（如：第1轮识别抗扰特征 → 第2轮进行条件推理 → 第3轮综合决策）。所有轮次的问题都必须针对同一张图片。" if is_multi_round else ""}
"""
    }

    # 🔧 扩展说明：添加新图片类型时，在这里添加对应的完整出题逻辑
    # prompts["video_frame"] = f"""
    # 你是一位专业的视觉推理评测出题专家。请基于这张图片的内容，设计一道【{question_type_name_cn}】。
    # 
    # **图片类型**: video_frame（视频帧类型）
    # **图片特点**：包含时间序列信息，是视频中的一帧。
    # **出题重点**：关注时间变化、动作识别、动态特征等。
    # **出题要求**：
    # 1. **深度推理**：...
    # 2. **时间分析**：...
    # 3. **思维链**：...
    # """
    
    return prompts.get(image_type, prompts["mixed"])  # 默认使用 mixed 类型

def get_question_type_specific_requirements(question_type: str, include_process: bool = True) -> str:
    """
    获取特定问题类型的要求和输出格式
    🔧 扩展说明：添加新问题类型时，只需在这里添加对应的要求
    注意：每次只生成一个问题，所以输出格式是单个对象，不是数组
    """
    requirements = {
        "single_choice": f"""
**格式规范**：必须提供 A, B, C, D 四个选项，其中只有一个是正确答案。

**输出格式**：
请严格返回一个 JSON 对象（不是数组）：
{{
    "question_type": "四选单选",
    "question": "问题内容...",
    "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
{("    \"qa_make_process\": \"推理过程...\",\n" if include_process else "")}    "answer": "一个选项字母"
}}
""",
        "multiple_choice": f"""
**格式规范**：必须提供 A, B, C, D 四个选项，其中至少有两个是正确答案。

**输出格式**：
请严格返回一个 JSON 对象（不是数组）：
{{
    "question_type": "四选多选",
    "question": "问题内容...",
    "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
{("    \"qa_make_process\": \"推理过程...\",\n" if include_process else "")}    "answer": "多个选项字母"  // 多个正确答案用字母组合，如 "AB", "ACD" 等
}}
""",
        "true_false": f"""
**格式规范**：判断题的选项固定为null，answer是 true 或者 false，

**输出格式**：
请严格返回一个 JSON 对象（不是数组）：
{{
    "question_type": "判断题",
    "question": "问题内容...",
    "options": null,
{("    \"qa_make_process\": \"推理过程...\",\n" if include_process else "")}    "answer": "true" 或者 "false" // true表示正确，false表示错误
}}
""",
        "essay": f"""
**答案简练**：答案必须是具体的实体名称、数字结果或关键短语。

**输出格式**：
请严格返回一个 JSON 对象（不是数组）：
{{
    "question_type": "问答题",
    "question": "问题内容...",
    "options": null,
{("    \"qa_make_process\": \"推理过程...\",\n" if include_process else "")}    "answer": "正确答案"
}}
""",
        "multi_round_single_choice": """
**格式规范**：多轮单选题需要设计多轮对话，每轮都是单选题，必须提供 A, B, C, D 四个选项。

**输出格式**：
请严格返回一个 JSON 对象（不是数组），包含 round1, round2, round3 等字段（根据指定的轮数生成对应数量的字段）。
""",
        "multi_round_essay": """
**格式规范**：多轮问答题需要设计多轮对话，每轮都是问答题，答案必须是具体的实体名称、数字结果或关键短语。

**输出格式**：
请严格返回一个 JSON 对象（不是数组），包含 round1, round2, round3 等字段（根据指定的轮数生成对应数量的字段）。
"""
    }
    
    # 🔧 扩展说明：添加新问题类型时，在这里添加对应的要求
    # requirements["fill_blank"] = """
    # **格式规范**：填空题需要提供空白位置，答案应简洁明确。
    # ...
    # """
    
    base_requirement = requirements.get(question_type, requirements["essay"])
    # 根据 include_process 参数动态调整输出格式
    if not include_process:
        # 移除 qa_make_process 字段
        base_requirement = base_requirement.replace('    "qa_make_process": "推理过程...",\n', '')
        base_requirement = base_requirement.replace('    "qa_make_process": {', '')
        base_requirement = base_requirement.replace('        {process_example}\n    },\n', '')
    return base_requirement


def build_prompt_template(image_type: str, question_type: str, rounds: int = 3, include_process: bool = True) -> str:
    """
    构建完整的提示词模板
    🔧 扩展说明：这个函数会自动组合所有部分，无需修改
    注意：现在只生成一个问题，所以不需要 count 参数
    提示词由两部分组成：图片类型出题逻辑 + 题目类型要求（包括输出格式）
    rounds: 多轮对话的轮数（仅用于多轮对话题型）
    """
    question_type_name_cn = QUESTION_TYPES.get(question_type, "问答题")
    
    # 组合两部分：图片类型出题逻辑 + 题目类型要求（包括输出格式）
    image_prompt = get_image_type_prompt(image_type, question_type_name_cn, rounds, include_process)
    type_requirements = get_question_type_specific_requirements(question_type, include_process)
    
    # 如果是多轮对话，动态生成输出格式示例
    if "multi_round" in question_type:
        # 生成轮数字段列表
        rounds_list = [f"round{i+1}" for i in range(rounds)]
        
        # 生成示例格式
        question_example = ",\n        ".join([f'"{r}": "第{i+1}轮问题内容..."' for i, r in enumerate(rounds_list)])
        
        if "single_choice" in question_type:
            # 多轮单选题
            options_example = ",\n        ".join([f'"{r}": {{"A": "...", "B": "...", "C": "...", "D": "..."}}' for r in rounds_list])
            answer_example = ",\n        ".join([f'"{r}": "一个选项字母"' for r in rounds_list])
            process_example = ",\n        ".join([f'"{r}": "第{i+1}轮推理过程..."' for i, r in enumerate(rounds_list)])
            
            process_part = f'    "qa_make_process": {{\n        {process_example}\n    }},\n' if include_process else ''
            format_example = f"""
**输出格式**：
请严格返回一个 JSON 对象（不是数组），包含 {rounds} 轮对话字段：
{{
    "question_type": "多轮单选题",
    "question": {{
        {question_example}
    }},
    "options": {{
        {options_example}
    }},
{process_part}    "answer": {{
        {answer_example}
    }}
}}
"""
        else:
            # 多轮问答题
            process_example = ",\n        ".join([f'"{r}": "第{i+1}轮推理过程..."' for i, r in enumerate(rounds_list)])
            answer_example = ",\n        ".join([f'"{r}": "第{i+1}轮答案"' for i, r in enumerate(rounds_list)])
            
            process_part = f'    "qa_make_process": {{\n        {process_example}\n    }},\n' if include_process else ''
            format_example = f"""
**输出格式**：
请严格返回一个 JSON 对象（不是数组），包含 {rounds} 轮对话字段：
{{
    "question_type": "多轮问答题",
    "question": {{
        {question_example}
    }},
    "options": null,
{process_part}    "answer": {{
        {answer_example}
    }}
}}
"""
        
        type_requirements = type_requirements + format_example
    
    # 拼接：图片类型提示词 + 题目类型要求
    prompt = image_prompt + type_requirements
    return prompt

# 初始化提示词模板系统（延迟生成，按需构建）
PROMPT_TEMPLATES = {}

def get_prompt_template(image_type: str, question_type: str, count: int = 1, rounds: int = 3, include_process: bool = True) -> str:
    """
    获取提示词模板（延迟生成，支持动态扩展）
    🔧 扩展说明：添加新类型后，这个函数会自动支持，无需修改
    注意：count 参数保留以兼容旧代码，但实际不再使用（每次只生成一个问题）
    rounds: 多轮对话的轮数（仅用于多轮对话题型）
    """
    # 对于多轮对话，需要包含轮数信息在缓存键中
    # 同时包含 include_process 信息，因为提示词内容会不同
    process_flag = "p1" if include_process else "p0"
    if "multi_round" in question_type:
        cache_key = f"{image_type}_{question_type}_r{rounds}_{process_flag}"
    else:
        cache_key = f"{image_type}_{question_type}_{process_flag}"
    
    if cache_key not in PROMPT_TEMPLATES:
        PROMPT_TEMPLATES[cache_key] = build_prompt_template(image_type, question_type, rounds, include_process)
    
    return PROMPT_TEMPLATES[cache_key]


# ==============================================================================
# 🛠️ 工具函数
# ==============================================================================
def get_next_version_path(original_path):
    if not os.path.exists(original_path): return original_path
    dir_name, file_name = os.path.split(original_path)
    base_name, ext = os.path.splitext(file_name)
    counter = 2
    while True:
        new_name = f"{base_name}_v{counter}{ext}"
        new_path = os.path.join(dir_name, new_name)
        if not os.path.exists(new_path): return new_path
        counter += 1

def init_log_file(log_dir: str, args) -> str:
    """
    初始化日志文件
    返回日志文件路径
    """
    global LOG_FILE, _log_full_display_count
    
    # 重置日志计数器
    _log_full_display_count = 0
    
    # 创建日志目录
    if not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    
    # 生成日志文件名（包含运行参数和时间戳）
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    
    log_filename = f"{timestamp}_{args.image_type}_{args.question_type}_n{args.num}"
    if "multi_round" in args.question_type:
        log_filename += f"_r{args.rounds}"
    log_filename += ".log"
    
    log_path = os.path.join(log_dir, log_filename)
    
    # 打开日志文件（追加模式）
    LOG_FILE = open(log_path, "w", encoding="utf-8")
    
    # 写入运行参数
    LOG_FILE.write("="*80 + "\n")
    LOG_FILE.write("📋 运行参数\n")
    LOG_FILE.write("="*80 + "\n")
    LOG_FILE.write(f"运行时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    LOG_FILE.write(f"输入文件: {args.input}\n")
    LOG_FILE.write(f"输出文件: {args.output}\n")
    LOG_FILE.write(f"图片类型: {args.image_type}\n")
    LOG_FILE.write(f"问题类型: {args.question_type}\n")
    LOG_FILE.write(f"每张图片生成问题数: {args.num}\n")
    if "multi_round" in args.question_type:
        LOG_FILE.write(f"多轮对话轮数: {args.rounds}\n")
    LOG_FILE.write(f"模型: {args.model}\n")
    LOG_FILE.write(f"API Base: {args.api_base}\n")
    LOG_FILE.write(f"温度: {args.temp}\n")
    LOG_FILE.write(f"最大Token数: {args.tokens}\n")
    LOG_FILE.write(f"并发线程数: {args.workers}\n")
    LOG_FILE.write(f"批量写入大小: {args.batch}\n")
    LOG_FILE.write(f"断点续传: {args.resume}\n")
    LOG_FILE.write(f"启用思考模式: {args.enable_thinking}\n")
    LOG_FILE.write(f"日志模式: {args.log_mode} ({'详细' if args.log_mode == 'detailed' else '简化'})\n")
    if args.log_mode == "detailed":
        LOG_FILE.write(f"日志优化: 提示词前 {_LOG_FULL_DISPLAY_LIMIT} 条完整显示，后续显示摘要；响应对象始终完整\n")
    else:
        LOG_FILE.write(f"日志优化: 前 {_LOG_FULL_DISPLAY_LIMIT} 条全部详细，后续全部简略\n")
    if args.limit:
        LOG_FILE.write(f"限制处理数量: {args.limit}\n")
    LOG_FILE.write("="*80 + "\n")
    LOG_FILE.write("\n")
    LOG_FILE.flush()
    
    return log_path

def log_model_response(image_id: str, question_index: int, response, prompt: str = "", api_time: float = 0):
    """
    记录模型返回的日志（支持详细/简化两种模式）
    优化：前N个完整显示，后续显示摘要
    api_time: API调用耗时（秒）
    """
    global LOG_FILE, _log_full_display_count, _LOG_FULL_DISPLAY_LIMIT
    
    if LOG_FILE is None:
        return
    
    log_mode = GLOBAL_CONFIG.get("log_mode", "simple")
    
    with log_lock:
        try:
            # 判断是否完整显示
            _log_full_display_count += 1
            is_full_display = _log_full_display_count <= _LOG_FULL_DISPLAY_LIMIT
            
            LOG_FILE.write(f"\n{'='*80}\n")
            LOG_FILE.write(f"[{time.strftime('%H:%M:%S')}] image_id:{image_id} | question_index:{question_index}\n")
            LOG_FILE.write(f"{'='*80}\n")
            
            if log_mode == "detailed":
                # 📝 详细模式：提示词前N个详细后面简略，但响应对象必须完全完整
                if is_full_display:
                    LOG_FILE.write("\n【提示词】\n")
                    LOG_FILE.write(prompt + "\n")
                    LOG_FILE.write(f"\n{'-'*80}\n")
                else:
                    # 省略版：只显示前200字符和总长度
                    prompt_preview = prompt[:200] + "..." if len(prompt) > 200 else prompt
                    LOG_FILE.write(f"\n【提示词摘要】（完整长度: {len(prompt)} 字符）\n")
                    LOG_FILE.write(prompt_preview + "\n")
                    LOG_FILE.write(f"\n{'-'*80}\n")
                
                # 响应对象：详细模式下必须完全完整，包含所有reasoning字段
                LOG_FILE.write("\n【模型响应 - 完整序列化】\n")
                
                try:
                    if hasattr(response, 'model_dump'):
                        response_dict = response.model_dump()
                    else:
                        response_dict = {
                            "id": getattr(response, 'id', None),
                            "object": getattr(response, 'object', None),
                            "created": getattr(response, 'created', None),
                            "model": getattr(response, 'model', None),
                        }
                        if hasattr(response, 'choices') and response.choices:
                            choice = response.choices[0]
                            choice_dict = {
                                "index": getattr(choice, 'index', None),
                                "finish_reason": getattr(choice, 'finish_reason', None),
                            }
                            if hasattr(choice, 'message'):
                                message = choice.message
                                message_dict = {
                                    "role": getattr(message, 'role', None),
                                    "content": getattr(message, 'content', None),
                                }
                                # 详细日志模式下：保留所有reasoning字段，不按优先级过滤
                                if hasattr(message, 'reasoning') and message.reasoning:
                                    message_dict["reasoning"] = message.reasoning
                                if hasattr(message, 'reasoning_content') and message.reasoning_content:
                                    message_dict["reasoning_content"] = message.reasoning_content
                                if hasattr(message, 'reasoning_details') and message.reasoning_details:
                                    message_dict["reasoning_details"] = message.reasoning_details
                                choice_dict["message"] = message_dict
                            response_dict["choices"] = [choice_dict]
                        
                        if hasattr(response, 'usage'):
                            response_dict["usage"] = {
                                "prompt_tokens": getattr(response.usage, 'prompt_tokens', None),
                                "completion_tokens": getattr(response.usage, 'completion_tokens', None),
                                "total_tokens": getattr(response.usage, 'total_tokens', None),
                            }
                    
                    # 详细模式下：响应对象必须完全完整
                    LOG_FILE.write(json.dumps(response_dict, indent=2, ensure_ascii=False, default=str))
                    LOG_FILE.write("\n")
                except Exception as e:
                    LOG_FILE.write(f"⚠️ 序列化失败: {e}\n")
                    LOG_FILE.write(f"响应字符串: {str(response)}\n")
            
            else:
                # 📝 简化模式：前几个全部详细，后面全部简略
                if is_full_display:
                    # 前几个：完整显示
                    LOG_FILE.write("\n【提示词】\n")
                    LOG_FILE.write(prompt + "\n")
                    LOG_FILE.write(f"\n{'-'*80}\n")
                    
                    LOG_FILE.write("\n【模型响应 - 完整序列化】\n")
                    try:
                        if hasattr(response, 'model_dump'):
                            response_dict = response.model_dump()
                        else:
                            response_dict = {
                                "id": getattr(response, 'id', None),
                                "object": getattr(response, 'object', None),
                                "created": getattr(response, 'created', None),
                                "model": getattr(response, 'model', None),
                            }
                            if hasattr(response, 'choices') and response.choices:
                                choice = response.choices[0]
                                choice_dict = {
                                    "index": getattr(choice, 'index', None),
                                    "finish_reason": getattr(choice, 'finish_reason', None),
                                }
                                if hasattr(choice, 'message'):
                                    message = choice.message
                                    message_dict = {
                                        "role": getattr(message, 'role', None),
                                        "content": getattr(message, 'content', None),
                                    }
                                    # 简化模式前几个：保留所有reasoning字段
                                    if hasattr(message, 'reasoning') and message.reasoning:
                                        message_dict["reasoning"] = message.reasoning
                                    if hasattr(message, 'reasoning_content') and message.reasoning_content:
                                        message_dict["reasoning_content"] = message.reasoning_content
                                    if hasattr(message, 'reasoning_details') and message.reasoning_details:
                                        message_dict["reasoning_details"] = message.reasoning_details
                                    choice_dict["message"] = message_dict
                                response_dict["choices"] = [choice_dict]
                            
                            if hasattr(response, 'usage'):
                                response_dict["usage"] = {
                                    "prompt_tokens": getattr(response.usage, 'prompt_tokens', None),
                                    "completion_tokens": getattr(response.usage, 'completion_tokens', None),
                                    "total_tokens": getattr(response.usage, 'total_tokens', None),
                                }
                        
                        LOG_FILE.write(json.dumps(response_dict, indent=2, ensure_ascii=False, default=str))
                        LOG_FILE.write("\n")
                    except Exception as e:
                        LOG_FILE.write(f"⚠️ 序列化失败: {e}\n")
                        LOG_FILE.write(f"响应字符串: {str(response)}\n")
                else:
                    # 后面：全部简略
                    if hasattr(response, 'choices') and response.choices:
                        message = response.choices[0].message
                        
                        # Content（省略显示）
                        if message.content:
                            content_len = len(message.content)
                            if content_len > 300:
                                content_preview = message.content[:300] + f"...(共{content_len}字符)"
                            else:
                                content_preview = message.content
                            LOG_FILE.write(f"\n【Content】({content_len}字符)\n{content_preview}\n")
                        
                        # 思考内容（按优先级：reasoning > reasoning_content > reasoning_details）
                        reasoning_text_to_log = None
                        reasoning_field_name = None
                        if hasattr(message, 'reasoning') and message.reasoning:
                            reasoning_text_to_log = message.reasoning
                            reasoning_field_name = "Reasoning"
                        elif hasattr(message, 'reasoning_content') and message.reasoning_content:
                            reasoning_text_to_log = message.reasoning_content
                            reasoning_field_name = "Reasoning Content"
                        elif hasattr(message, 'reasoning_details') and message.reasoning_details:
                            rd = message.reasoning_details
                            if isinstance(rd, list):
                                texts = []
                                for d in rd:
                                    if isinstance(d, dict):
                                        t = d.get('text', '')
                                        if t:
                                            texts.append(str(t).strip())
                                    elif isinstance(d, str) and d.strip():
                                        texts.append(d.strip())
                                if texts:
                                    reasoning_text_to_log = "\n\n".join(texts)
                                    reasoning_field_name = "Reasoning Details"
                            elif isinstance(rd, str) and rd.strip():
                                reasoning_text_to_log = rd.strip()
                                reasoning_field_name = "Reasoning Details"
                        
                        if reasoning_text_to_log:
                            reasoning_len = len(reasoning_text_to_log)
                            if reasoning_len > 300:
                                reasoning_preview = reasoning_text_to_log[:300] + f"...(共{reasoning_len}字符)"
                            else:
                                reasoning_preview = reasoning_text_to_log
                            LOG_FILE.write(f"\n【{reasoning_field_name}】({reasoning_len}字符)\n{reasoning_preview}\n")
                    
                    # Token使用情况
                    LOG_FILE.write(f"\n{'-'*80}\n")
                    if hasattr(response, 'usage') and response.usage:
                        usage = response.usage
                        prompt_tokens = getattr(usage, 'prompt_tokens', 0)
                        completion_tokens = getattr(usage, 'completion_tokens', 0)
                        total_tokens = getattr(usage, 'total_tokens', 0)
                        LOG_FILE.write(f"【Token使用】输入:{prompt_tokens} | 输出:{completion_tokens} | 总计:{total_tokens}\n")
                    else:
                        LOG_FILE.write(f"【Token使用】无usage信息\n")
                    
                    # API耗时
                    LOG_FILE.write(f"【API耗时】{api_time:.2f}秒\n")
            
            LOG_FILE.write(f"{'='*80}\n\n")
            
            # 每5次才flush一次（批量写入）
            if question_index % 5 == 0:
                LOG_FILE.flush()
        except Exception as e:
            # 日志失败不影响主流程，静默处理
            pass

def close_log_file():
    """
    关闭日志文件
    """
    global LOG_FILE
    if LOG_FILE:
        with log_lock:
            try:
                LOG_FILE.write("="*80 + "\n")
                LOG_FILE.write(f"日志结束时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                LOG_FILE.write("="*80 + "\n")
                LOG_FILE.close()
                LOG_FILE = None
            except:
                pass

def encode_image(image_path):
    """
    编码图片为 Base64，并返回 MIME 类型
    
    Returns:
        tuple: (base64_string, mime_type) 或 (None, None) 如果失败
    """
    try:
        if not os.path.exists(image_path):
            return None, None
        
        # 根据文件后缀判断 MIME 类型
        ext = os.path.splitext(image_path)[1].lower()
        mime_types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
            '.bmp': 'image/bmp',
            '.tiff': 'image/tiff',
            '.tif': 'image/tiff',
        }
        mime_type = mime_types.get(ext, 'image/jpeg')  # 默认使用 jpeg
        
        with open(image_path, "rb") as image_file:
            base64_str = base64.b64encode(image_file.read()).decode('utf-8')
            return base64_str, mime_type
    except:
        return None, None

def write_jsonl_item(item):
    """JSONL 格式：实时写入单条数据（逐行追加）"""
    global OUTPUT_FORMAT
    if OUTPUT_FORMAT != "jsonl":
        return False
    
    with file_lock:
        try:
            with open(OUTPUT_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
            return True
        except Exception as e:
            print(f"❌ [JSONL实时写入失败] {e}")
            return False

def flush_buffer():
    """批量写入缓冲区数据到文件（仅用于 JSON 格式，JSONL 格式不使用此函数）"""
    global result_buffer, OUTPUT_FORMAT
    
    # JSONL 格式不使用 buffer，直接返回
    if OUTPUT_FORMAT == "jsonl":
        return
    
    with buffer_lock:
        if not result_buffer: 
            return
        current_batch = list(result_buffer)
        result_buffer = [] 
    
    flush_start = time.time()
    
    with file_lock:
        try:
            # JSON 格式：需要读取整个文件，合并后写入
            data = []
            
            # 读取现有数据
            if os.path.exists(OUTPUT_PATH):
                try:
                    with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
                        content = f.read().strip()
                        if content: 
                            data = json.loads(content)
                except Exception as e:
                    print(f"⚠️ [读取失败] {e}")
                    data = []
            
            data.extend(current_batch)
            
            # 写入数据
            with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            flush_time = time.time() - flush_start
            
            # 只在异常情况下才打印详细信息
            if flush_time > 2.0:
                file_size_mb = os.path.getsize(OUTPUT_PATH) / 1024 / 1024
                print(f"\n⚠️ [JSON保存慢] +{len(current_batch)}题 耗时{flush_time:.1f}s 文件{file_size_mb:.1f}MB")
                if file_size_mb > 10:
                    print(f"   💡 建议：使用 .jsonl 格式（逐行追加，无需batch）或增大--batch参数（当前{GLOBAL_CONFIG['batch_size']}）")
        except Exception as e: 
            print(f"❌ [保存失败] {e}")

def signal_handler(signum, frame):
    """
    信号处理函数：处理 Ctrl+C (SIGINT) 和 SIGTERM 信号
    确保在中断时也能保存 JSON 格式的 buffer 数据
    """
    global shutdown_event, OUTPUT_FORMAT
    
    print("\n\n⚠️  检测到中断信号 (Ctrl+C)，正在优雅关闭...")
    print("   📝 正在保存已处理的数据（JSON格式会保存buffer中的数据）...")
    
    # 设置关闭标志
    shutdown_event.set()
    
    # 立即刷新 JSON 格式的 buffer（JSONL 格式已经是实时写入的，无需处理）
    if OUTPUT_FORMAT == "json":
        print("   💾 正在保存 JSON buffer 中的数据...")
        flush_buffer()
        print("   ✅ JSON buffer 已保存")
    else:
        print("   ✅ JSONL 格式已经是实时写入，无需额外保存")
    
    # 关闭日志文件
    close_log_file()
    
    print("   ✅ 数据已保存，正在退出...")
    sys.exit(0)

# ==============================================================================
# 🧠 核心生成逻辑
# ==============================================================================

def generate_single_qa(item, image_type, question_type, question_index, total_count, base64_image_cache=None, mime_type_cache=None):
    """
    生成单个问题（一次对话生成一个问题）
    输入: 
        - item: 单个图片信息
        - image_type: 图片类型
        - question_type: 问题类型
        - question_index: 当前问题索引（从0开始）
        - total_count: 总共要生成的问题数
        - base64_image_cache: Base64编码的图片（可选，如果提供则不再重新编码）
        - mime_type_cache: 图片的MIME类型（可选，与base64_image_cache一起使用）
    输出: 单个问答对字典，如果失败返回 None
    """
    # 性能诊断：记录各阶段耗时
    stage_times = {}
    total_start = time.time()
    
    image_path = item.get("image_path")
    original_id = str(item.get("id", "unknown"))
    
    # 确保 image_type 从 item 中获取或使用传入的参数
    item_image_type = item.get("image_type") or item.get("type") or image_type
    
    # 如果提供了缓存的 base64，直接使用；否则重新编码
    if base64_image_cache is not None and mime_type_cache is not None:
        base64_image = base64_image_cache
        mime_type = mime_type_cache
    else:
        base64_image, mime_type = encode_image(image_path)
        if not base64_image:
            return None
        # 如果 mime_type 为 None，使用默认值
        if not mime_type:
            mime_type = 'image/jpeg'

    # 获取对应组合的提示词模板（每次生成1个问题）
    template_key = item_image_type.lower()
    # 如果图片类型不在支持的列表中（排除"all"），默认使用 mixed
    valid_image_types = [t for t in IMAGE_TYPES if t != "all"]
    if template_key not in valid_image_types:
        template_key = "mixed"  # 默认使用 mixed
    
    question_type_key = question_type.lower()
    if question_type_key not in QUESTION_TYPES:
        question_type_key = "essay"
    
    # 获取轮数（仅用于多轮对话题型）
    rounds = GLOBAL_CONFIG["rounds"]
    
    # 使用新的模板构建函数（每次只生成一个问题）
    include_process = GLOBAL_CONFIG.get("include_process", True)
    prompt = get_prompt_template(template_key, question_type_key, rounds=rounds, include_process=include_process)

    # 获取配置参数（这些key在main()中已确保存在）
    max_retries = int(GLOBAL_CONFIG["max_retries"])
    base_sleep = float(GLOBAL_CONFIG["retry_sleep"])
    timeout = float(GLOBAL_CONFIG["request_timeout"])

    for attempt in range(max_retries):
        try:
            # 构建 API 调用参数
            api_params = {
                "model": GLOBAL_CONFIG["model_name"],
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{base64_image}"}},
                        ],
                    }
                ],
                "max_tokens": GLOBAL_CONFIG["max_tokens"],
                "timeout": timeout,
            }
            # 仅当显式配置了温度时才传递，避免覆盖模型默认值
            if GLOBAL_CONFIG.get("temperature") is not None:
                api_params["temperature"] = GLOBAL_CONFIG["temperature"]
            
            # 如果启用思考模式，添加 extra_body
            if GLOBAL_CONFIG.get("enable_thinking", False):
                api_params["extra_body"] = {"enable_thinking": True}
            
            # 性能诊断：记录API调用时间
            api_start = time.time()
            response = client.chat.completions.create(**api_params)
            api_time = time.time() - api_start
            stage_times['api_call'] = api_time
            
            # 记录模型返回日志（仅在需要时）
            if LOG_FILE:
                log_model_response(original_id, question_index, response, prompt, api_time)
            
            content = response.choices[0].message.content.strip() if response.choices[0].message.content else ""
            message = response.choices[0].message
            
            # ==================== 智能提取 JSON 和思考内容 ====================
            # 核心逻辑：
            # 1. 优先从 content 中提取 JSON（大多数模型都在这里输出）
            # 2. content 中除 JSON 外的部分都当作思考过程
            # 3. 如果 content 中没有 JSON，再从 reasoning_content 中提取
            # 4. 合并所有思考内容
            
            qa_data = None
            json_source = None
            thinking_parts = []  # 存储所有思考内容
            
            # 📝 辅助函数：从文本中提取 JSON（终极优化版）
            def extract_json_from_text(text, source_name):
                """
                从文本中提取 JSON，返回 (json_data, before_text, after_text)
                json_data: 解析后的 JSON 对象
                before_text: JSON 前的文本（思考过程）
                after_text: JSON 后的文本（思考过程）
                
                优化策略：
                1. 最优先检测thinking模型格式（</think>标签）- 零开销检测
                2. 快速路径：直接解析常见格式
                3. 通用路径：正则+栈匹配（仅作为fallback）
                """
                if not text:
                    return None, "", ""
                
                # 🔧 辅助函数：快速找到JSON结束位置（使用栈匹配，忽略字符串内部）
                def find_json_end_fast(s):
                    """快速找到JSON对象/数组的结束位置，O(n)时间复杂度"""
                    if not s or s[0] not in ['{', '[']:
                        return -1
                    
                    stack = [s[0]]
                    pairs = {'}': '{', ']': '['}
                    in_string = False
                    escape = False
                    
                    for i in range(1, len(s)):
                        c = s[i]
                        
                        if escape:
                            escape = False
                            continue
                        
                        if c == '\\':
                            escape = True
                            continue
                        
                        if c == '"':
                            in_string = not in_string
                            continue
                        
                        if in_string:
                            continue
                        
                        if c in ['{', '[']:
                            stack.append(c)
                        elif c in ['}', ']']:
                            if not stack or stack[-1] != pairs[c]:
                                return -1
                            stack.pop()
                            if not stack:
                                return i + 1
                    
                    return -1
                
                # 🚀 方法0: Thinking模型专用 - 超快速提取（优先级最高）
                # 格式：思考过程</think>\nJSON内容（最常见）
                # 检测成本：O(n) 子串查找，但通常很快因为</think>在前半部分
                think_end_pos = text.find("</think>")
                if think_end_pos != -1:
                    # 找到</think>标签，直接分割（零额外内存分配）
                    thinking = text[:think_end_pos].strip()
                    # 移除可能的 <think> 开头标签（如果有）
                    if thinking.startswith("<think>"):
                        thinking = thinking[7:].strip()
                    
                    # JSON部分从</think>后开始（+8是</think>的长度）
                    json_start = think_end_pos + 8
                    json_part = text[json_start:].strip()
                    
                    # 快速路径1：直接是JSON对象/数组（最常见，80%+的情况）
                    if json_part and (json_part[0] == '{' or json_part[0] == '['):
                        # 使用栈快速找到JSON结束位置
                        json_end = find_json_end_fast(json_part)
                        if json_end > 0:
                            json_str = json_part[:json_end]
                            try:
                                json_data = json.loads(json_str)
                                after = json_part[json_end:].strip()
                                return json_data, thinking, after
                            except:
                                pass  # 解析失败，继续尝试
                    
                    # 快速路径2：在```json代码块中
                    json_marker = json_part.find("```json")
                    if json_marker != -1:
                        json_content_start = json_marker + 7  # len("```json")
                        json_content_end = json_part.find("```", json_content_start)
                        if json_content_end != -1:
                            json_str = json_part[json_content_start:json_content_end].strip()
                            try:
                                json_data = json.loads(json_str)
                                after = json_part[json_content_end + 3:].strip()
                                return json_data, thinking, after
                            except:
                                pass
                    
                    # 快速路径3：在普通```代码块中
                    code_marker = json_part.find("```")
                    if code_marker != -1:
                        json_content_start = code_marker + 3
                        json_content_end = json_part.find("```", json_content_start)
                        if json_content_end != -1:
                            json_str = json_part[json_content_start:json_content_end].strip()
                            if json_str and (json_str[0] == '{' or json_str[0] == '['):
                                try:
                                    json_data = json.loads(json_str)
                                    after = json_part[json_content_end + 3:].strip()
                                    return json_data, thinking, after
                                except:
                                    pass
                    
                    # 如果快速路径都失败，说明格式异常
                    # 不再继续尝试，直接返回None（避免浪费时间）
                    return None, thinking, ""
                
                # 方法1: 提取 ```json``` 代码块（次优先）
                json_marker = text.find("```json")
                if json_marker != -1:
                    before = text[:json_marker].strip()
                    json_content_start = json_marker + 7
                    json_content_end = text.find("```", json_content_start)
                    if json_content_end != -1:
                        json_str = text[json_content_start:json_content_end].strip()
                        after = text[json_content_end + 3:].strip()
                        try:
                            json_data = json.loads(json_str)
                            return json_data, before, after
                        except:
                            # ```json``` 存在但解析失败，直接返回（不再尝试其他方法）
                            return None, before, after
                
                # 方法2: 提取普通 ``` 代码块
                code_marker = text.find("```")
                if code_marker != -1:
                    before = text[:code_marker].strip()
                    json_content_start = code_marker + 3
                    json_content_end = text.find("```", json_content_start)
                    if json_content_end != -1:
                        json_str = text[json_content_start:json_content_end].strip()
                        after = text[json_content_end + 3:].strip()
                        if json_str and (json_str[0] == '{' or json_str[0] == '['):
                            try:
                                json_data = json.loads(json_str)
                                return json_data, before, after
                            except:
                                pass
                
                # 方法3: 直接解析整个文本（常见于纯JSON输出）
                text_stripped = text.strip()
                if text_stripped and (text_stripped[0] == '{' or text_stripped[0] == '['):
                    try:
                        json_data = json.loads(text_stripped)
                        return json_data, "", ""
                    except:
                        # 可能JSON后面有额外内容，使用栈匹配
                        json_end = find_json_end_fast(text_stripped)
                        if json_end > 0:
                            json_str = text_stripped[:json_end]
                            after = text_stripped[json_end:].strip()
                            try:
                                json_data = json.loads(json_str)
                                return json_data, "", after
                            except:
                                pass
                
                # 方法4: 查找文本中的JSON（最慢，仅作为fallback）
                for i, char in enumerate(text):
                    if char in ['{', '[']:
                        json_end = find_json_end_fast(text[i:])
                        if json_end > 0:
                            before = text[:i].strip()
                            json_str = text[i:i+json_end]
                            after = text[i+json_end:].strip()
                            try:
                                json_data = json.loads(json_str)
                                return json_data, before, after
                            except:
                                continue
                
                # 所有方法都失败
                return None, "", ""
            
            # 性能诊断：记录JSON提取时间
            extract_start = time.time()
            
            # 🔍 步骤1: 优先从 content 中提取 JSON
            if content:
                json_data_temp, before_text, after_text = extract_json_from_text(content, "content")
                
                if json_data_temp is not None:
                    qa_data = json_data_temp
                    json_source = "content"
                    
                    # content 中 JSON 前后的文本都是思考过程
                    if before_text:
                        thinking_parts.append(("content前段", before_text))
                    if after_text:
                        thinking_parts.append(("content后段", after_text))
                else:
                    # 如果 content 整体不是 JSON，全部作为思考过程
                    if content:
                        thinking_parts.append(("content全文", content))
            
            # 📝 辅助函数：获取思考内容字段（静默模式，按优先级：reasoning > reasoning_content > reasoning_details）
            def get_reasoning_content():
                """从 response 对象的多个可能位置获取思考内容，按优先级只返回一个"""
                # 优先级1：reasoning
                if hasattr(message, 'reasoning') and message.reasoning:
                    return message.reasoning.strip()
                elif hasattr(response, 'reasoning') and response.reasoning:
                    return response.reasoning.strip()
                # 优先级2：reasoning_content
                elif hasattr(message, 'reasoning_content') and message.reasoning_content:
                    return message.reasoning_content.strip()
                elif hasattr(response, 'reasoning_content') and response.reasoning_content:
                    return response.reasoning_content.strip()
                # 优先级3：reasoning_details（可能是列表或字符串）
                elif hasattr(message, 'reasoning_details') and message.reasoning_details:
                    rd = message.reasoning_details
                    if isinstance(rd, list):
                        texts = []
                        for d in rd:
                            if isinstance(d, dict):
                                t = d.get('text', '')
                                if t:
                                    texts.append(str(t).strip())
                            elif isinstance(d, str) and d.strip():
                                texts.append(d.strip())
                        if texts:
                            return "\n\n".join(texts)
                    elif isinstance(rd, str) and rd.strip():
                        return rd.strip()
                elif hasattr(response, 'reasoning_details') and response.reasoning_details:
                    rd = response.reasoning_details
                    if isinstance(rd, list):
                        texts = []
                        for d in rd:
                            if isinstance(d, dict):
                                t = d.get('text', '')
                                if t:
                                    texts.append(str(t).strip())
                            elif isinstance(d, str) and d.strip():
                                texts.append(d.strip())
                        if texts:
                            return "\n\n".join(texts)
                    elif isinstance(rd, str) and rd.strip():
                        return rd.strip()
                return None
            
            # 🔍 步骤2: 如果 content 中没找到 JSON，再从 reasoning_content 中找
            if qa_data is None:
                reasoning_content = get_reasoning_content()
                
                if reasoning_content:
                    json_data_temp, before_text, after_text = extract_json_from_text(reasoning_content, "reasoning_content")
                    
                    if json_data_temp is not None:
                        qa_data = json_data_temp
                        json_source = "reasoning_content"
                        
                        # reasoning_content 中 JSON 前后的文本都是思考过程
                        if before_text:
                            thinking_parts.append(("reasoning前段", before_text))
                        if after_text:
                            thinking_parts.append(("reasoning后段", after_text))
                    else:
                        # 如果 reasoning_content 整体不是 JSON，全部作为思考过程
                        thinking_parts.append(("reasoning全文", reasoning_content))
            else:
                # 如果已经从 content 中提取到了 JSON，但也有 reasoning_content，
                # 则将 reasoning_content 全部作为思考过程
                reasoning_content = get_reasoning_content()
                
                if reasoning_content:
                    thinking_parts.append(("reasoning字段", reasoning_content))
            
            # 🔍 步骤3: 如果还是没找到 JSON，报错
            if qa_data is None:
                error_msg = "无法从 content 或 reasoning_content 中提取 JSON 格式的问答数据"
                if content:
                    error_msg += f"\ncontent 内容: {content[:200]}..."
                if thinking_parts:
                    error_msg += f"\n找到 {len(thinking_parts)} 段思考内容，但没有 JSON"
                raise ValueError(error_msg)
            
            # 📦 步骤4: 合并所有思考内容
            final_reasoning_content = ""
            if thinking_parts:
                formatted_parts = []
                for label, text in thinking_parts:
                    formatted_parts.append(f"【{label}】\n{text}")
                final_reasoning_content = "\n\n".join(formatted_parts)
            
            # 性能统计
            extract_time = time.time() - extract_start
            stage_times['json_extract'] = extract_time
            
            # 7️⃣ 统一处理：如果是数组，取第一个；如果是对象，直接使用
            if isinstance(qa_data, list):
                if len(qa_data) > 0:
                    qa_data = qa_data[0]  # 取第一个
                else:
                    raise ValueError("返回的 JSON 数组为空")
            elif isinstance(qa_data, dict):
                pass  # 对象格式，直接使用
            else:
                raise ValueError(f"无法识别的 JSON 格式: {type(qa_data)}")

            # 判断是否为多轮对话题型
            is_multi_round = "multi_round" in question_type_key
            
            if is_multi_round:
                # 多轮对话：一次性提取所有字段（减少字典访问）
                question_dict = qa_data.get("question", {})
                options_dict = qa_data.get("options", {})
                answer_dict = qa_data.get("answer", {})
                process_dict = qa_data.get("qa_make_process") or qa_data.get("process", {})
                question_type_text = qa_data.get("question_type", "问答题")
                
                # 如果启用了思考模式且有推理内容，合并到每轮的 qa_make_process
                include_process = GLOBAL_CONFIG.get("include_process", True)
                if include_process:
                    if GLOBAL_CONFIG.get("enable_thinking", False) and final_reasoning_content:
                        if not isinstance(process_dict, dict):
                            process_dict = {}
                        
                        rounds = GLOBAL_CONFIG["rounds"]
                        thinking_prefix = f"【模型思考推理过程】\n{final_reasoning_content}"
                        
                        # 批量处理所有轮次（避免重复字符串拼接）
                        for i in range(rounds):
                            round_key = f"round{i+1}"
                            round_process = process_dict.get(round_key, "")
                            process_dict[round_key] = f"{thinking_prefix}\n\n【问题解答过程】\n{round_process}" if round_process else thinking_prefix
                    elif not isinstance(process_dict, dict):
                        process_dict = {f"round{i+1}": "" for i in range(GLOBAL_CONFIG["rounds"])}
                
                new_item = {
                    "image_id": str(original_id),
                    "image_path": image_path,
                    "image_type": item_image_type,
                    "question_id": f"{original_id}_{question_type}_{question_index}",
                    "question_type": QUESTION_TYPES.get(question_type_key, question_type_text),
                    "question": question_dict,
                    "options": options_dict or None,
                    "answer": answer_dict,
                }
                # 只有在需要时才添加 qa_make_process 字段
                if include_process:
                    new_item["qa_make_process"] = process_dict if isinstance(process_dict, dict) else ""
            else:
                # 单轮对话：保持原有格式
                # 优化：一次性提取所有需要的字段，减少字典访问
                process_from_qa = qa_data.get("qa_make_process") or qa_data.get("process", "")
                question_text = qa_data.get("question", "")
                options_data = qa_data.get("options")
                answer_text = qa_data.get("answer", "")
                question_type_text = qa_data.get("question_type", "问答题")
                
                # 如果启用了思考模式且有推理内容，合并到 qa_make_process
                include_process = GLOBAL_CONFIG.get("include_process", True)
                if include_process:
                    if GLOBAL_CONFIG.get("enable_thinking", False) and final_reasoning_content:
                        qa_make_process = f"【模型思考推理过程】\n{final_reasoning_content}\n\n【问题解答过程】\n{process_from_qa}" if process_from_qa else f"【模型思考推理过程】\n{final_reasoning_content}"
                    else:
                        qa_make_process = process_from_qa
                
                new_item = {
                    "image_id": str(original_id),
                    "image_path": image_path,
                    "image_type": item_image_type,
                    "question_id": f"{original_id}_{question_type}_{question_index}",
                    "question_type": QUESTION_TYPES.get(question_type_key, question_type_text),
                    "question": question_text,
                    "options": options_data,
                    "answer": answer_text,
                }
                # 只有在需要时才添加 qa_make_process 字段
                if include_process:
                    new_item["qa_make_process"] = qa_make_process
            
            # 打印每道题的API耗时和Token信息
            api_time = stage_times.get('api_call', 0)
            
            # 获取token使用信息
            if hasattr(response, 'usage') and response.usage:
                prompt_tokens = getattr(response.usage, 'prompt_tokens', 0)
                completion_tokens = getattr(response.usage, 'completion_tokens', 0)
                total_tokens = getattr(response.usage, 'total_tokens', 0)
                print(f"✅ [Q{question_index+1}] image_id={original_id} | API耗时:{api_time:.2f}s | Token: 输入{prompt_tokens} + 输出{completion_tokens} = {total_tokens}")
            else:
                print(f"✅ [Q{question_index+1}] image_id={original_id} | API耗时:{api_time:.2f}s | Token: N/A")
            
            return new_item

        except Exception as e:
            # 获取简要错误信息（只取第一行）
            error_msg = str(e).split('\n')[0][:100]  # 限制长度
            
            # 如果还有重试机会，则等待一段时间（指数退避）
            if attempt < max_retries - 1:
                sleep_seconds = base_sleep * (2 ** attempt)
                print(f"⚠️ [Q{question_index+1}] image_id={original_id} | 失败(尝试{attempt + 1}/{max_retries}): {error_msg} | {sleep_seconds:.1f}s后重试")
                try:
                    time.sleep(sleep_seconds)
                except Exception:
                    pass
            else:
                print(f"❌ [Q{question_index+1}] image_id={original_id} | 失败(已重试{max_retries}次): {error_msg}")
                return None


def generate_qa_data(item, image_type, question_type):
    """
    输入: 
        - item: 单个图片信息
        - image_type: 图片类型 (pure_image, pure_text, mixed, splice, stacked)
        - question_type: 问题类型 (single_choice, multiple_choice, true_false, essay)
    输出: 一个 List (生成的 N 个问答对)
    
    注意：现在是多次对话，每次生成一个问题
    优化：图片只编码一次，避免重复 I/O 操作
    """
    count = GLOBAL_CONFIG["questions_per_image"]
    generated_items = []
    
    image_id = str(item.get("id", "unknown"))
    image_path = item.get("image_path")
    
    # 优化：只编码一次图片，避免重复 I/O（当每张图生成多个问题时）
    base64_image, mime_type = encode_image(image_path)
    if not base64_image:
        print(f"❌ [图片] image_id={image_id} | 图片编码失败: {image_path}")
        return []
    
    # 如果 mime_type 为 None，使用默认值
    if not mime_type:
        mime_type = 'image/jpeg'
    
    # 多次对话，每次生成一个问题（复用已编码的图片）
    for question_index in range(count):
        qa_item = generate_single_qa(
            item, 
            image_type, 
            question_type, 
            question_index, 
            count,
            base64_image_cache=base64_image,
            mime_type_cache=mime_type
        )
        if qa_item:
            generated_items.append(qa_item)
        # 失败信息已经在 generate_single_qa 中输出了，这里不需要重复
    
    return generated_items

def worker(item, total_images=0):
    """线程工作单元（优化版：减少锁竞争）"""
    global CURRENT_IMAGE_TYPE, CURRENT_QUESTION_TYPE, progress_bar, OUTPUT_FORMAT, shutdown_event
    
    # 检查是否需要关闭
    if shutdown_event.is_set():
        return
    
    image_id = str(item.get("id", "unknown"))
    image_path = item.get("image_path", "")
    expected_count = GLOBAL_CONFIG["questions_per_image"]
    
    results = generate_qa_data(item, CURRENT_IMAGE_TYPE, CURRENT_QUESTION_TYPE)
    
    # 再次检查是否需要关闭（处理过程中可能收到中断信号）
    if shutdown_event.is_set():
        # 如果使用 JSON 格式，需要保存当前结果到 buffer（会在信号处理中统一保存）
        if OUTPUT_FORMAT == "json" and results:
            with buffer_lock:
                result_buffer.extend(results)
        return
    
    # 优化：合并锁操作，减少锁获取次数
    need_flush = False
    
    if results:
        # 检查是否有部分失败
        actual_count = len(results)
        if actual_count < expected_count:
            print(f"⚠️ [图片] image_id={image_id} | 部分成功: {actual_count}/{expected_count}题")
        
        # JSONL 格式：实时写入每条结果
        # JSON 格式：放入 buffer，达到 batch_size 时批量写入
        if OUTPUT_FORMAT == "jsonl":
            # JSONL：每条实时写入
            for result_item in results:
                write_jsonl_item(result_item)
            
            # 更新统计（不需要 buffer）
            with buffer_lock:
                stats["success"] += len(results)
                stats["questions_generated"] += len(results)
                stats["images_processed"] += 1
                stats["images_success"] += 1
        else:
            # JSON：使用 buffer 批量写入
            with buffer_lock:
                result_buffer.extend(results)
                stats["success"] += len(results)
                stats["questions_generated"] += len(results)
                stats["images_processed"] += 1
                stats["images_success"] += 1
                
                if len(result_buffer) >= GLOBAL_CONFIG["batch_size"]:
                    need_flush = True
            
            if need_flush:
                flush_buffer()
        
        # 每张图片处理完都更新进度条
        if progress_bar:
            with progress_lock:
                progress_bar.update(1)
                progress_bar.set_postfix({
                    "成功": stats['images_success'],
                    "失败": stats['images_failed'],
                    "题数": stats['questions_generated']
                })
    else:
        # 整张图片所有问题都失败
        print(f"❌ [图片] image_id={image_id} | 所有问题生成失败({expected_count}/{expected_count})")
        
        with buffer_lock:
            stats["failed"] += 1
            stats["images_failed"] += 1
            stats["images_processed"] += 1
        
        # 每张图片处理完都更新进度条
        if progress_bar:
            with progress_lock:
                progress_bar.update(1)
                progress_bar.set_postfix({
                    "成功": stats['images_success'],
                    "失败": stats['images_failed'],
                    "题数": stats['questions_generated']
                })

# ==============================================================================
# 🚀 主程序
# ==============================================================================
##添加新题型和图片类型，这里面要加
def main():
    global client, OUTPUT_PATH, CURRENT_IMAGE_TYPE, CURRENT_QUESTION_TYPE
    
    parser = argparse.ArgumentParser(description="问题生成模块 - 根据 image_type 和 question_type 生成题目")
    parser.add_argument("--input", required=True, help="输入JSON文件路径")
    parser.add_argument("--output", required=True, help="输出JSON文件路径")
    parser.add_argument("--image_type", default="mixed", choices=IMAGE_TYPES, 
                       help="图片类型: pure_image, pure_text, mixed, splice, stacked, all (all表示处理所有类型，不筛选)")
    parser.add_argument("--question_type", default="essay", 
                       choices=["single_choice", "multiple_choice", "true_false", "essay", "multi_round_single_choice", "multi_round_essay"],
                       help="问题类型: single_choice(四选单选), multiple_choice(四选多选), true_false(判断题), essay(问答题), multi_round_single_choice(多轮单选题), multi_round_essay(多轮问答题)")
    parser.add_argument("--num", type=int, default=GLOBAL_CONFIG["questions_per_image"], 
                       help=f"每张图片生成的问题数量（默认: {GLOBAL_CONFIG['questions_per_image']}）")
    parser.add_argument("--rounds", type=int, default=GLOBAL_CONFIG["rounds"], 
                       help=f"多轮对话的轮数（仅用于多轮对话题型，默认{GLOBAL_CONFIG['rounds']}轮）")
    parser.add_argument("--resume", action="store_true", help="断点续传")
    parser.add_argument("--limit", type=int, default=None, help="限制处理的图片数量")
    parser.add_argument("--random", action="store_true",
                       help="随机选择样本：如果设置了 --limit，则随机选择 N 个；否则随机打乱顺序")
    parser.add_argument("--seed", type=int, default=None,
                       help="随机种子：用于可复现的随机选择（仅当 --random 启用时有效）")
    
    # API Params (默认值引用 GLOBAL_CONFIG，统一配置管理)
    parser.add_argument("--api_base", default="http://localhost:22002/v1")
    parser.add_argument("--api_key", default="EMPTY")
    parser.add_argument("--model", default="Qwen3-VL-235B")
    parser.add_argument(
        "--temp",
        type=float,
        default=None,
        help="温度参数（可选，不设置则使用模型默认温度）",
    )
    parser.add_argument("--tokens", type=int, default=GLOBAL_CONFIG["max_tokens"],
                       help=f"最大Token数（默认: {GLOBAL_CONFIG['max_tokens']}）")
    parser.add_argument("--batch", type=int, default=GLOBAL_CONFIG["batch_size"],
                       help=f"json批量写入大小（默认: {GLOBAL_CONFIG['batch_size']}）")
    parser.add_argument("--workers", type=int, default=GLOBAL_CONFIG["max_workers"],
                       help=f"并发线程数（默认: {GLOBAL_CONFIG['max_workers']}）")
    parser.add_argument("--enable_thinking", action="store_true", 
                       help="启用思考模式（会提取 reasoning_content 并合并到 qa_make_process）")
    parser.add_argument("--timeout", type=float, default=GLOBAL_CONFIG["request_timeout"],
                       help=f"单次请求超时时间（秒），默认{GLOBAL_CONFIG['request_timeout']}s")
    parser.add_argument("--retries", type=int, default=GLOBAL_CONFIG["max_retries"],
                       help=f"请求失败时的最大重试次数，默认{GLOBAL_CONFIG['max_retries']}次")
    parser.add_argument("--retry_sleep", type=float, default=GLOBAL_CONFIG["retry_sleep"],
                       help=f"请求失败后的基础重试间隔（秒），默认{GLOBAL_CONFIG['retry_sleep']}s，后续按指数退避")
    parser.add_argument("--log_dir", type=str, default="./logs", 
                       help="日志文件保存目录（默认: ./logs）")
    parser.add_argument("--log_mode", type=str, default="simple", choices=["simple", "detailed"],
                       help="日志模式: simple(简化，只记录关键信息+token数) 或 detailed(详细，记录完整响应)")
    parser.add_argument("--no_process", action="store_true",
                       help="不生成 qa_make_process 字段（推理过程），只生成问题、选项和答案")
    
    args = parser.parse_args()

    # 注册信号处理函数（处理 Ctrl+C 和 SIGTERM）
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 注入配置
    GLOBAL_CONFIG["api_base"] = args.api_base
    GLOBAL_CONFIG["api_key"] = args.api_key
    GLOBAL_CONFIG["model_name"] = args.model
    GLOBAL_CONFIG["temperature"] = args.temp
    GLOBAL_CONFIG["max_tokens"] = args.tokens
    GLOBAL_CONFIG["batch_size"] = args.batch
    GLOBAL_CONFIG["max_workers"] = args.workers
    GLOBAL_CONFIG["questions_per_image"] = args.num
    GLOBAL_CONFIG["enable_thinking"] = args.enable_thinking
    GLOBAL_CONFIG["rounds"] = args.rounds
    GLOBAL_CONFIG["request_timeout"] = args.timeout
    GLOBAL_CONFIG["max_retries"] = args.retries
    GLOBAL_CONFIG["retry_sleep"] = args.retry_sleep
    GLOBAL_CONFIG["log_mode"] = args.log_mode
    GLOBAL_CONFIG["include_process"] = not args.no_process  # 如果设置了 --no_process，则 include_process 为 False
    
    CURRENT_IMAGE_TYPE = args.image_type
    CURRENT_QUESTION_TYPE = args.question_type
    client = OpenAI(api_key=GLOBAL_CONFIG["api_key"], base_url=GLOBAL_CONFIG["api_base"])
    
    # 初始化日志文件
    log_path = init_log_file(args.log_dir, args)
    print(f"📝 [日志] 日志文件: {log_path}")
    print(f"📝 [日志模式] {'📋 详细模式(完整响应)' if args.log_mode == 'detailed' else '⚡ 简化模式(关键信息+token)'}")
    
    if args.enable_thinking:
        print("🧠 [配置] 已启用思考模式 (enable_thinking=True)")
    
    if "multi_round" in args.question_type:
        print(f"🔄 [配置] 多轮对话题型，轮数: {args.rounds}")

    # 路径与断点续传
    if args.resume:
        OUTPUT_PATH = args.output
        print(f"🔄 [断点续传] {OUTPUT_PATH}")
    else:
        OUTPUT_PATH = get_next_version_path(args.output)
        print(f"🆕 [全新运行] {OUTPUT_PATH}")
    
    # 根据文件扩展名自动判断输出格式
    global OUTPUT_FORMAT
    if OUTPUT_PATH.lower().endswith('.jsonl'):
        OUTPUT_FORMAT = "jsonl"
        print(f"📝 [格式] 检测到 .jsonl 扩展名，使用 JSONL 格式（实时逐行追加写入）")
        print(f"   💡 JSONL 格式优势：每条结果实时写入，无需buffer，batch参数不生效")
        # 如果是全新运行且文件已存在，清空文件（JSONL 追加模式需要）
        if not args.resume and os.path.exists(OUTPUT_PATH):
            with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
                pass  # 清空文件
    else:
        OUTPUT_FORMAT = "json"
        print(f"📝 [格式] 使用 JSON 格式（批量保存，batch={GLOBAL_CONFIG['batch_size']}）")
        print(f"   💡 提示：如需处理大量数据，建议使用 .jsonl 格式（逐行追加，性能更好）")

    if not os.path.exists(args.input):
        print(f"❌ 输入不存在: {args.input}")
        return
    
    # 根据文件扩展名自动判断输入格式
    input_format = "jsonl" if args.input.lower().endswith('.jsonl') else "json"
    
    if input_format == "jsonl":
        # JSONL 格式：逐行读取
        print(f"📥 [输入格式] 检测到 .jsonl 扩展名，使用 JSONL 格式读取")
        input_data = []
        with open(args.input, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                    input_data.append(item)
                except json.JSONDecodeError as e:
                    print(f"⚠️ 警告：第 {line_num} 行JSON解析失败: {e}，跳过")
                    continue
        print(f"📥 [输入] 从 JSONL 文件读取到 {len(input_data)} 条数据")
    else:
        # JSON 格式：标准读取
        print(f"📥 [输入格式] 使用 JSON 格式读取")
        with open(args.input, "r", encoding="utf-8") as f:
            input_data = json.load(f)
        # 处理不同的 JSON 结构
        if isinstance(input_data, dict) and "items" in input_data:
            input_data = input_data["items"]
        elif not isinstance(input_data, list):
            print(f"❌ 错误：输入 JSON 格式不正确，期望数组或包含 'items' 字段的对象")
            return
        print(f"📥 [输入] 从 JSON 文件读取到 {len(input_data)} 条数据")

    # 自动创建父目录
    output_dir = os.path.dirname(OUTPUT_PATH)
    if output_dir and not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir, exist_ok=True)
            print(f"📁 自动创建缺失的目录: {output_dir}")
        except Exception as e:
            print(f"❌ 无法创建目录: {e}")
            return

    # 断点续传：读取已处理的图片ID（基于 image_id 判断，支持 JSON 和 JSONL）
    processed_ids = set()
    if args.resume and os.path.exists(OUTPUT_PATH):
        try:
            if OUTPUT_FORMAT == "jsonl":
                # JSONL 格式：逐行读取
                with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            x = json.loads(line)
                            # image_id 现在直接就是原始ID，不需要分割
                            # 兼容旧格式：如果存在 id 字段也支持（旧格式可能是 "orig_id_index"）
                            image_id = str(x.get("image_id", ""))
                            if not image_id:
                                # 兼容旧格式：从 id 字段提取（格式可能是 "orig_id_index"）
                                old_id = str(x.get("id", ""))
                                if "_" in old_id:
                                    parts = old_id.rsplit("_", 1)
                                    image_id = parts[0]
                                else:
                                    image_id = old_id
                            if image_id:
                                processed_ids.add(image_id)
                        except json.JSONDecodeError:
                            continue  # 跳过无效行
            else:
                # JSON 格式：标准读取
                with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                    for x in existing:
                        # image_id 现在直接就是原始ID，不需要分割
                        # 兼容旧格式：如果存在 id 字段也支持（旧格式可能是 "orig_id_index"）
                        image_id = str(x.get("image_id", ""))
                        if not image_id:
                            # 兼容旧格式：从 id 字段提取（格式可能是 "orig_id_index"）
                            old_id = str(x.get("id", ""))
                            if "_" in old_id:
                                parts = old_id.rsplit("_", 1)
                                image_id = parts[0]
                            else:
                                image_id = old_id
                        if image_id:
                            processed_ids.add(image_id)
            print(f"📊 [断点续传] 从输出文件中读取到 {len(processed_ids)} 张已处理的图片")
        except Exception as e:
            print(f"⚠️ [断点续传] 读取已处理图片列表失败: {e}")
            processed_ids = set()

    # 第一步：根据 image_type 筛选图片（如果设置了具体类型）
    filtered_data = []
    if CURRENT_IMAGE_TYPE.lower() == "all":
        # 如果设置为 "all"，不进行筛选，处理所有图片
        print(f"📋 [筛选] 图片类型设置为 'all'，将处理所有类型的图片（不筛选）")
        filtered_data = input_data
    else:
        # 筛选指定类型的图片
        print(f"📋 [筛选] 只处理图片类型为 '{CURRENT_IMAGE_TYPE}' 的图片")
        for item in input_data:
            # 从 item 中获取图片类型（支持 image_type 或 type 字段）
            item_image_type = item.get("image_type") or item.get("type", "")
            if item_image_type:
                item_image_type = item_image_type.lower()
            else:
                item_image_type = ""
            
            # 匹配图片类型（不区分大小写）
            if item_image_type == CURRENT_IMAGE_TYPE.lower():
                filtered_data.append(item)
        print(f"📋 [筛选] 从 {len(input_data)} 张图片中筛选出 {len(filtered_data)} 张 '{CURRENT_IMAGE_TYPE}' 类型的图片")
    
    # 第二步：过滤已处理的项（仅在开启断点续传时跳过）
    todo_items = []
    skipped_count = 0
    for item in filtered_data:
        item_id = str(item.get("id", ""))
        # 只有在开启断点续传时才跳过已处理的项
        if args.resume and item_id in processed_ids:
            skipped_count += 1
            continue
        
        # 确保 item 中有 image_type 字段（用于后续生成时使用）
        item_image_type = item.get("image_type") or item.get("type")
        if not item_image_type:
            # 如果输入数据中没有 image_type，使用当前设置的类型（除非是"all"）
            if CURRENT_IMAGE_TYPE.lower() != "all":
                item_image_type = CURRENT_IMAGE_TYPE
            else:
                item_image_type = "mixed"  # 默认使用 mixed
        item["image_type"] = item_image_type
        todo_items.append(item)
    
    if skipped_count > 0:
        print(f"📋 [断点续传] 跳过已处理的 {skipped_count} 张图片")
    
    # 显示最终待处理列表信息
    if CURRENT_IMAGE_TYPE.lower() == "all":
        print(f"📋 [最终] 待处理图片: {len(todo_items)} 张（所有类型）")
    else:
        print(f"📋 [最终] 待处理图片: {len(todo_items)} 张（仅 '{CURRENT_IMAGE_TYPE}' 类型）")
    
    # 应用 LIMIT 限制和随机选择
    # 重要：limit 是本次运行要处理的数量，不是累计总数
    # 逻辑：
    #   - 如果开启了断点续传：先过滤掉已处理的图片，然后从剩余图片中选择 limit 数量
    #   - 如果没有开启断点续传：直接从所有图片中选择 limit 数量
    # 使用局部变量避免与 random 模块名混淆
    use_random = args.random
    original_todo_count = len(todo_items)
    if args.limit:
        # limit 是本次运行要处理的数量，直接使用 limit
        print(f"✂️  [限制] 本次运行将处理 {args.limit} 张图片")
        
        if use_random:
            # 随机选择
            if args.seed is not None:
                random.seed(args.seed)
                print(f"🎲 [随机选择] 使用随机种子: {args.seed}")
            if args.limit < len(todo_items):
                todo_items = random.sample(todo_items, args.limit)
                print(f"🎲 [随机选择] 从 {original_todo_count} 个待处理图片中随机选择 {args.limit} 张")
            else:
                print(f"📊 [限制] 限制数量 {args.limit} 大于等于待处理图片数 {original_todo_count}，处理全部")
        else:
            # 按顺序选择前 N 个
            if args.limit < len(todo_items):
                todo_items = todo_items[:args.limit]
                print(f"📊 [限制] 按顺序选择前 {args.limit} 张图片（共 {original_todo_count} 张待处理）")
            else:
                print(f"📊 [限制] 限制数量 {args.limit} 大于等于待处理图片数 {original_todo_count}，处理全部")
    elif use_random:
        # 如果设置了 use_random 但没有 limit，则随机打乱顺序
        if args.seed is not None:
            random.seed(args.seed)
            print(f"🎲 [随机打乱] 使用随机种子: {args.seed}")
        random.shuffle(todo_items)
        print(f"🎲 [随机打乱] 已打乱 {len(todo_items)} 张待处理图片的顺序")

    total_images = len(todo_items)
    total_questions_expected = total_images * args.num
    
    print(f"📋 任务: {total_images} 图 x {args.num} 题 = {total_questions_expected} 题")
    print(f"📋 图片类型: {CURRENT_IMAGE_TYPE}, 问题类型: {QUESTION_TYPES.get(CURRENT_QUESTION_TYPE, CURRENT_QUESTION_TYPE)}")
    print(f"📋 并发: {args.workers}")
    print("="*80)
    
    if not todo_items:
        print("✅ 无需处理")
        return

    start_time = time.time()
    
    # 初始化进度条
    global progress_bar
    if TQDM_AVAILABLE:
        progress_bar = tqdm(
            total=total_images,
            desc="处理图片",
            unit="图",
            ncols=120,
            bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}] {postfix}',
            initial=0
        )
        # 初始化后缀显示
        progress_bar.set_postfix({
            "已处理": f"0/{total_images}",
            "成功图": "0",
            "失败图": "0",
            "总题数": "0"
        })
    else:
        print(f"🚀 开始处理 {total_images} 张图片...")
        progress_bar = None
    
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=GLOBAL_CONFIG['max_workers']) as executor:
            # 使用 submit 而不是 map，以便更好地控制进度
            futures = {executor.submit(worker, item, total_images): item for item in todo_items}
            
            # 等待所有任务完成（检查关闭标志）
            for future in concurrent.futures.as_completed(futures):
                # 如果收到中断信号，取消未完成的任务
                if shutdown_event.is_set():
                    print("\n⚠️  正在取消未完成的任务...")
                    for f in futures:
                        f.cancel()
                    break
                
                try:
                    future.result()  # 获取结果，如果有异常会抛出
                except Exception as e:
                    # 如果是因为关闭导致的异常，忽略
                    if shutdown_event.is_set():
                        break
                    item = futures[future]
                    error_msg = str(e).split('\n')[0][:100]  # 限制长度
                    print(f"❌ [图片] image_id={item.get('id', 'unknown')} | 处理异常: {error_msg}")
                    with buffer_lock:
                        stats["failed"] += 1
                        stats["images_failed"] += 1
                        stats["images_processed"] += 1
                    if progress_bar:
                        with progress_lock:
                            progress_bar.update(1)
                            progress_bar.set_postfix({
                                "成功": stats['images_success'],
                                "失败": stats['images_failed'],
                                "题数": stats['questions_generated']
                            })
    
    except KeyboardInterrupt:
        # 捕获 KeyboardInterrupt（虽然信号处理已经处理了，但这里作为双重保险）
        print("\n⚠️  检测到 KeyboardInterrupt，正在保存数据...")
        shutdown_event.set()
    finally:
        # 确保最后刷新缓冲区（JSON格式会保存buffer中的数据，JSONL格式已经是实时写入的）
        if OUTPUT_FORMAT == "json":
            print("💾 正在保存 JSON buffer 中的剩余数据...")
        flush_buffer()
        
        # 关闭进度条
        if progress_bar:
            progress_bar.close()
            progress_bar = None
        
        # 关闭日志文件
        close_log_file()
    
    elapsed_time = time.time() - start_time
    print("\n" + "="*80)
    print("✅ 处理完成!")
    print(f"⏱️  总耗时: {elapsed_time:.2f}s ({elapsed_time/60:.2f}分钟)")
    print(f"📊 处理统计:")
    print(f"   - 图片总数: {total_images} 张")
    print(f"   - 已处理图片: {stats['images_processed']} 张")
    print(f"   - 成功图片: {stats['images_success']} 张 ({stats['images_success']/max(stats['images_processed'], 1)*100:.1f}%)")
    print(f"   - 失败图片: {stats['images_failed']} 张 ({stats['images_failed']/max(stats['images_processed'], 1)*100:.1f}%)")
    print(f"   - 生成问题数: {stats['questions_generated']}/{total_questions_expected} 题")
    print(f"   - 问题生成率: {stats['questions_generated']/max(total_questions_expected, 1)*100:.1f}%")
    if stats['images_processed'] > 0:
        avg_time = elapsed_time / stats['images_processed']
        print(f"   - 平均每图: {avg_time:.2f}s")
        if stats['questions_generated'] > 0:
            avg_time_per_q = elapsed_time / stats['questions_generated']
            print(f"   - 平均每题: {avg_time_per_q:.2f}s")
    print("="*80)

if __name__ == "__main__":
    main()