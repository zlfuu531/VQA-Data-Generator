import argparse
import json
import os
import random
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

from qa_make import GLOBAL_CONFIG, QUESTION_TYPES, encode_image, get_prompt_template


def _extract_json_block(text: str) -> Optional[Dict[str, Any]]:
    """从模型返回的文本中提取首个 JSON 对象，容错处理引号与空白。"""
    if not text:
        return None
    start = text.find("{")
    if start == -1:
        return None

    stack = []
    in_string = False
    escape = False
    for idx, ch in enumerate(text[start:], start=start):
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
        if in_string:
            continue
        if ch == "{":
            stack.append(ch)
        elif ch == "}":
            if not stack:
                return None
            stack.pop()
            if not stack:
                try:
                    return json.loads(text[start : idx + 1])
                except Exception:
                    return None
    return None


def _ensure_client(client: Optional[OpenAI] = None) -> OpenAI:
    """优先使用传入 client，否则根据 GLOBAL_CONFIG 构建。"""
    if client:
        return client
    return OpenAI(
        api_key=GLOBAL_CONFIG.get("api_key") or os.environ.get("API_KEY", ""),
        base_url=GLOBAL_CONFIG.get("api_base", ""),
    )


def _get_step1_prompt(image_type: str, question_type: str, rounds: int = 3, include_process: bool = True) -> str:
    """第一步：出题prompt"""
    question_type_name_cn = QUESTION_TYPES.get(question_type, "问答题")
    is_multi_round = "multi_round" in question_type
    rounds_text = f"{rounds}轮" if is_multi_round else ""
    
    # 根据image_type选择不同的prompt模板
    if image_type == "splice":
        base_prompt = f"""
你是一名顶级的金融多模态高难度 VQA 题目构建专家，擅长从复杂的"图表+文字说明"类金融图像中，设计需要多层逻辑链条的专业级分析题。

**特别说明**：给定图像为**两张金融图片的拼接**，这两张图片可能互不相关。请**只针对其中一张图片的内容出题**，出题内容要和另一张图片的内容尽可能不相干，目的是考察模型的**精准定位能力**（能否准确识别和聚焦于特定图片区域）。

请基于选定的那张金融图像（可能包含折线图、柱状图、饼图、同比/环比数据、百分比结构、表格、说明文字、指标定义、图例、注释等），生成一道【{question_type_name_cn}】。题目难度需显著高于一般金融研究员水平，必须依赖所选图片中多个信息块的交叉使用（图表 + 文字说明 + 注释 + 图例）。

**【任务要求】**

1. **题目难度需达到金融分析师/研究员水平**
   必须生成需要多步推理的金融推理问题，问题的答案只能依赖图像中的内容得到。题目类型可以包括但不限于：
   - 财务指标推理（基于图中数据进行计算或逻辑推断）
   - 图表趋势分析与推断（识别拐点、加速/减速、周期性等）
   - 结构化图形推理（如股权结构、资产结构、业务构成等）
   - 多实体关系推断（比较、排序、关联分析等）
   - 比较类问题（增长最快、占比最高、结构变化、相对表现等）
   - 经济或业务含义推断（基于图中客观信息得出结论）
   - 跨图表综合分析（在所选图片内，多项指标之间的链式推断，如 A→B→C）

2. **所有问题必须满足**：
   - 答案唯一、客观、可验证（不能有歧义或多种解释）
   - 必须严格依赖所选图片中的信息（不能依赖另一张图片或图外知识）
   - 题干不得直接给出图片内已有的结构化数据或结论
   - 题干需要通过描述让模型明确知道是针对哪张图片出题（如"上图""下图""左图""右图"或通过图片主题描述）
   - 不允许主观类问题（如"你怎么看""是否合理"）
   - 不允许开放式回答（如"列出可能的原因""可能有哪些影响"）

3. **难度要求：每一题至少满足以下任意两条**：
   - 涉及跨年度、跨季度、跨区域的趋势比较
   - 同时使用图表数值 + 图例解释 + 文字说明
   - 多指标之间的链式推理（A→B→C，需要至少 2-3 步推理）
   - 结构占比变化推断（如"哪部分贡献最大""结构如何变化"）
   - 从同比 + 环比的叠加信息得出判断
   - 使用所选图片中的多个图块（如主图 + 子图 + 表格）综合推断

4. **精准定位要求（重要）**：
   - 题干必须明确指向其中一张图片，避免模糊不清
   - 可以使用位置描述词（上图/下图/左图/右图）或主题描述（如"关于XX的图表"）
   - 答案必须只能从所选图片中得出，不能混用两张图片的信息
   - 推理过程要明确说明从所选图片的哪些位置获取了哪些信息

5. **思维链要求**：
   必须在 qa_make_process 字段中详细记录解题的完整推理链条，包括：
   - 明确说明针对的是哪张图片（如"基于上图"或"基于关于XX的图表"）
   - 从该图片的哪些位置获取了哪些信息
   - 如何将这些信息组合起来进行推理
   - 每一步的计算或逻辑判断过程
   - 最终如何得出答案

6. **严禁的行为**：
   - 不得混用两张图片的信息进行出题或作答
   - 不得编造图中不存在的数据、图例、时间刻度、指标名称
   - 不得在题干中直接泄露图中的关键数据或结论
   - 不得设计依赖外部知识或背景才能回答的问题
   - 不得设计答案模糊或有多种可能解释的问题

{"7. **多轮对话要求**：需要设计" + rounds_text + "轮对话，每轮都有独立的问题和答案，形成完整的对话流程。每轮问题都应遵循上述所有要求，且各轮之间应形成逻辑递进或关联（如：第1轮识别数据 → 第2轮计算指标 → 第3轮综合判断）。所有轮次的问题都必须针对同一张图片。" if is_multi_round else ""}
"""
    else:
        base_prompt = f"""
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

6. **思维链要求**：
   必须在 qa_make_process 字段中详细记录解题的完整推理链条，包括：
   - 从图中哪些位置获取了哪些信息
   - 如何将这些信息组合起来进行推理
   - 每一步的计算或逻辑判断过程
   - 最终如何得出答案

7. **严禁的行为**：
   - 不得在题干中直接泄露图中的关键数据或结论
   - 不得设计依赖外部知识或背景才能回答的问题
   - 不得设计答案模糊或有多种可能解释的问题
   - 不得设计主观性较强的推断预测问题，答案必须要有明确依据,例如折线图不得出估算数值、预测趋势等问题。

{"8. **多轮对话要求**：需要设计" + rounds_text + "轮对话，每轮都有独立的问题和答案，形成完整的对话流程。每轮问题都应遵循上述所有要求，且各轮之间应形成逻辑递进或关联（如：第1轮识别数据 → 第2轮计算指标 → 第3轮综合判断）。" if is_multi_round else ""}
"""
    
    # 添加输出格式要求
    type_requirements = get_prompt_template(image_type, question_type, rounds=rounds, include_process=include_process)
    # 提取类型要求部分（去掉图片类型部分）
    if "**【任务要求】**" in type_requirements:
        type_part = type_requirements.split("**【任务要求】**")[-1]
    else:
        type_part = type_requirements
    
    return base_prompt + "\n\n" + type_part


def _get_step2_prompt() -> str:
    """第二步：答案检验prompt"""
    return """
你是一名专业的金融题目质量检验专家，负责检验题目的答案是否正确、推理过程是否合理。

**【任务要求】**

请仔细检查给定的题目、答案和推理过程，判断答案是否正确。你需要：

1. **答案正确性检验**：
   - 检查答案是否可以从图像中推导得出
   - 验证推理过程中的每一步是否合理
   - 确认所有使用的数据是否真实存在于图像中
   - 检查计算过程是否正确（如有计算）
   - 验证逻辑推理是否严密

2. **推理过程完整性检验**：
   - 检查qa_make_process是否详细记录了每一步推理
   - 确认推理链条是否完整，没有跳跃
   - 验证每一步是否都有明确的依据（来自图像的哪些位置）

3. **输出格式**：
   请输出JSON格式：
   {
       "status": "pass" 或 "fail",
       "reason": "检验通过的原因" 或 "检验不通过的具体原因（详细说明哪里有问题）",
       "issues": ["问题1", "问题2", ...],  // 如果不通过，列出所有问题
       "suggestions": "如何修正的建议"  // 如果不通过，提供修正建议
   }

4. **判断标准**：
   - 如果答案正确、推理过程完整且合理，返回 status="pass"
   - 如果答案错误、推理过程有漏洞、使用了图像中不存在的数据，返回 status="fail"
   - 如果存在任何不确定或模糊的地方，返回 status="fail"

请基于给定的题目、答案和推理过程进行检验。
"""


def _get_step3_prompt() -> str:
    """第三步：题目质量提升prompt"""
    return """
你是一名专业的金融多模态VQA题目质量评估专家，负责评估和提升题目的质量，确保题目能够有效考察模型的图文理解、计算推理和识图能力。

**【任务要求】**

请对给定的题目进行全面质量评估，重点关注以下几个方面：

1. **图文联系质量**：
   - 题目是否充分利用了图像中的信息（图表、文字、图例、注释等）
   - 是否要求模型同时理解图像和文字说明
   - 是否避免了仅依赖单一信息源就能回答的问题
   - 图文信息的结合是否自然、必要

2. **计算步骤质量**：
   - 计算题是否涉及多步推理（至少2-3步）
   - 计算过程是否复杂且有意义（不只是简单加减乘除）
   - 是否涉及金融领域的专业计算（如增长率、占比、比率、加权平均等）
   - 计算步骤是否清晰可验证

3. **识图能力要求**：
   - 是否考察了模型对图像元素的识别能力（颜色、数字、标签、图例等）
   - **重要**：如果是折线图，不得出需要从折线图读取数值的题目（只能使用明确标注的数据）
   - 是否要求识别图表类型、坐标轴含义、图例对应关系等
   - 识图要求是否与推理要求有机结合

4. **题目难度与区分度**：
   - 题目难度是否达到金融分析师/研究员水平
   - 是否能够有效区分不同能力的模型
   - 是否避免了过于简单或过于困难的问题

5. **输出格式**：
   请输出JSON格式：
   {
       "status": "pass" 或 "fail",
       "quality_score": 0-100,  // 质量评分
       "issues": {
           "image_text_connection": "图文联系方面的问题（如有）",
           "calculation_steps": "计算步骤方面的问题（如有）",
           "image_recognition": "识图能力方面的问题（如有）",
           "difficulty": "难度方面的问题（如有）"
       },
       "suggestions": "如何提升质量的建议",
       "improved_question": {  // 如果不通过，提供改进后的题目（完整JSON对象）
           // 完整的题目对象，包括question, answer, options, qa_make_process等
       }
   }

6. **判断标准**：
   - 如果题目在图文联系、计算步骤、识图要求等方面都达到高质量标准，返回 status="pass"
   - 如果任何方面存在不足，返回 status="fail" 并提供改进建议
   - 特别关注：折线图题目是否违反了"不得出读数题目"的要求

请基于给定的题目和图像进行质量评估。
"""


def _get_step4_prompt() -> str:
    """第四步：整体质量检测prompt"""
    return """
你是一名顶级的金融多模态VQA题目最终质量审核专家，负责对题目进行整体质量检测，确保最终产出的是高质量金融多模态推理难题。

**【任务要求】**

请对给定的题目进行最终整体质量检测，重点关注：

1. **答案整体正确性**：
   - 答案是否完全正确，没有任何错误
   - 答案是否唯一、客观、可验证
   - 是否存在多种可能的解释或歧义
   - 选择题的选项是否合理，干扰项是否有效

2. **问题质量**：
   - 问题表述是否清晰、准确、专业
   - 问题是否避免了直接泄露答案或关键信息
   - 问题是否符合金融领域的实际应用场景
   - 问题是否能够有效考察模型的推理能力

3. **难度评估**：
   - 题目难度是否达到金融分析师/研究员水平
   - 是否涉及多步推理和复杂计算
   - 是否充分利用了图像中的多个信息源
   - 难度是否适中（不会过于简单或过于困难）

4. **整体一致性**：
   - 问题、答案、推理过程是否一致
   - 推理过程是否能够支撑答案
   - 所有字段是否完整且格式正确

5. **输出格式**：
   请输出JSON格式：
   {
       "status": "pass" 或 "fail",
       "overall_score": 0-100,  // 整体质量评分
       "correctness_score": 0-100,  // 答案正确性评分
       "quality_score": 0-100,  // 问题质量评分
       "difficulty_score": 0-100,  // 难度评分
       "issues": {
           "correctness": "答案正确性方面的问题（如有）",
           "question_quality": "问题质量方面的问题（如有）",
           "difficulty": "难度方面的问题（如有）",
           "consistency": "一致性问题（如有）"
       },
       "final_verdict": "最终判断：是否达到高质量金融多模态推理难题的标准",
       "suggestions": "如果需要改进，提供具体建议",
       "improved_question": {  // 如果不通过，提供最终改进后的题目（完整JSON对象）
           // 完整的题目对象，包括question, answer, options, qa_make_process等
       },
       "should_go_back_to": "step1" 或 "step3" 或 null  // 如果不通过，建议回到哪一步
   }

6. **判断标准**：
   - 如果题目在答案正确性、问题质量、难度等方面都达到高质量标准，返回 status="pass"
   - 如果存在任何问题，返回 status="fail"
   - 如果主要是答案或推理过程的问题，建议回到 step1
   - 如果主要是质量提升方面的问题，建议回到 step3

请基于给定的题目、答案、推理过程和图像进行最终质量检测。
"""


def _call_model_with_image(
    client: OpenAI, prompt: str, base64_image: str, mime_type: str
) -> Dict[str, Any]:
    resp = client.chat.completions.create(
        model=GLOBAL_CONFIG.get("model_name"),
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{base64_image}"}},
                ],
            }
        ],
        max_tokens=GLOBAL_CONFIG.get("max_tokens", 8192),
        temperature=GLOBAL_CONFIG.get("temperature", 0.7),
        timeout=GLOBAL_CONFIG.get("request_timeout", 1000.0),
    )
    message = resp.choices[0].message
    return {
        "raw": message.content or "",
        "json": _extract_json_block(message.content or ""),
        "usage": getattr(resp, "usage", None),
    }


def generate_adversarial_qa(
    item: Dict[str, Any],
    image_type: str,
    question_type: str,
    max_rounds: int = 3,
    client: Optional[OpenAI] = None,
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    使用“出题者A vs 答题者B”对抗式迭代，自动找到“最难但可答”的题目。
    输入/输出字段完全复用 qa_make.py 的格式；返回 (最终问答字典, 迭代轨迹)。
    """
    qa_client = _ensure_client(client)

    base64_image, mime_type = encode_image(item.get("image_path", ""))
    if not base64_image:
        return None, []
    mime_type = mime_type or "image/jpeg"

    rounds = GLOBAL_CONFIG.get("rounds", 3)
    include_process = GLOBAL_CONFIG.get("include_process", True)
    
    trace: List[Dict[str, Any]] = []
    final_payload: Optional[Dict[str, Any]] = None
    current_question: Optional[Dict[str, Any]] = None
    
    step1_prompt = _get_step1_prompt(image_type, question_type, rounds=rounds, include_process=include_process)
    
    iteration = 0
    max_iterations = max_rounds * 10  # 防止无限循环
    
    while iteration < max_iterations:
        iteration += 1
        
        # ========== 第一步：出题 ==========
        step1_input = (
            f"{step1_prompt}\n\n"
            "请输出JSON格式，包含完整的题目对象：\n"
            "{\n"
            '    "question": "...",\n'
            '    "answer": "...",\n'
            '    "options": [...],  // 如果是选择题\n'
            '    "qa_make_process": "...",  // 详细的推理过程\n'
            '    "question_type": "..."\n'
            "}\n"
        )
        
        step1_resp = _call_model_with_image(qa_client, step1_input, base64_image, mime_type)
        step1_json = step1_resp.get("json") or {}
        
        if not isinstance(step1_json, dict) or "question" not in step1_json:
            trace.append({
                "iteration": iteration,
                "step": 1,
                "status": "failed",
                "error": "无法解析题目JSON或缺少必要字段",
                "raw_response": step1_resp.get("raw", "")[:500]
            })
            if iteration >= 3:  # 连续失败3次则退出
                break
            continue
        
        current_question = step1_json
        trace.append({
            "iteration": iteration,
            "step": 1,
            "status": "completed",
            "question_preview": step1_json.get("question", "")[:100]
        })
        
        # ========== 第二步：答案检验 ==========
        step2_prompt = _get_step2_prompt()
        step2_input = (
            f"【题目】\n{json.dumps(current_question, ensure_ascii=False, indent=2)}\n\n"
            f"{step2_prompt}"
        )
        
        step2_resp = _call_model_with_image(qa_client, step2_input, base64_image, mime_type)
        step2_json = step2_resp.get("json") or {}
        step2_status = step2_json.get("status", "unknown")
        
        trace.append({
            "iteration": iteration,
            "step": 2,
            "status": step2_status,
            "reason": step2_json.get("reason", ""),
            "issues": step2_json.get("issues", [])
        })
        
        if step2_status == "fail":
            # 不通过，回到第一步，添加修正建议
            suggestions = step2_json.get("suggestions", "")
            step1_prompt = _get_step1_prompt(image_type, question_type, rounds=rounds, include_process=include_process)
            if suggestions:
                step1_prompt += f"\n\n【修正要求】\n{suggestions}\n【问题列表】\n" + "\n".join(f"- {issue}" for issue in step2_json.get("issues", []))
            continue
        
        # ========== 第三步：题目质量提升 ==========
        step3_prompt = _get_step3_prompt()
        step3_input = (
            f"【题目】\n{json.dumps(current_question, ensure_ascii=False, indent=2)}\n\n"
            f"{step3_prompt}"
        )
        
        step3_resp = _call_model_with_image(qa_client, step3_input, base64_image, mime_type)
        step3_json = step3_resp.get("json") or {}
        step3_status = step3_json.get("status", "unknown")
        
        trace.append({
            "iteration": iteration,
            "step": 3,
            "status": step3_status,
            "quality_score": step3_json.get("quality_score"),
            "issues": step3_json.get("issues", {})
        })
        
        if step3_status == "fail":
            # 不通过，使用改进后的题目或回到第一步
            improved = step3_json.get("improved_question")
            if isinstance(improved, dict) and "question" in improved:
                current_question = improved
                trace.append({
                    "iteration": iteration,
                    "step": 3,
                    "action": "used_improved_question"
                })
                # 继续到第四步
            else:
                # 回到第一步，添加质量提升建议
                suggestions = step3_json.get("suggestions", "")
                step1_prompt = _get_step1_prompt(image_type, question_type, rounds=rounds, include_process=include_process)
                if suggestions:
                    step1_prompt += f"\n\n【质量提升要求】\n{suggestions}"
                continue
        
        # ========== 第四步：整体质量检测 ==========
        step4_prompt = _get_step4_prompt()
        step4_input = (
            f"【题目】\n{json.dumps(current_question, ensure_ascii=False, indent=2)}\n\n"
            f"{step4_prompt}"
        )
        
        step4_resp = _call_model_with_image(qa_client, step4_input, base64_image, mime_type)
        step4_json = step4_resp.get("json") or {}
        step4_status = step4_json.get("status", "unknown")
        
        trace.append({
            "iteration": iteration,
            "step": 4,
            "status": step4_status,
            "overall_score": step4_json.get("overall_score"),
            "final_verdict": step4_json.get("final_verdict", "")
        })
        
        if step4_status == "pass":
            # 通过所有检验，返回最终题目
            final_payload = current_question
            break
        else:
            # 不通过，根据建议回到相应步骤
            go_back_to = step4_json.get("should_go_back_to", "step1")
            improved = step4_json.get("improved_question")
            
            if isinstance(improved, dict) and "question" in improved:
                current_question = improved
                trace.append({
                    "iteration": iteration,
                    "step": 4,
                    "action": "used_improved_question",
                    "go_back_to": go_back_to
                })
                # 如果建议回到step3，从step3重新开始
                if go_back_to == "step3":
                    continue  # 会重新执行step3
                # 如果建议回到step1，重新开始
                elif go_back_to == "step1":
                    suggestions = step4_json.get("suggestions", "")
                    step1_prompt = _get_step1_prompt(image_type, question_type, rounds=rounds, include_process=include_process)
                    if suggestions:
                        step1_prompt += f"\n\n【最终修正要求】\n{suggestions}"
                    continue
            else:
                # 没有提供改进版本，回到第一步
                suggestions = step4_json.get("suggestions", "")
                step1_prompt = _get_step1_prompt(image_type, question_type, rounds=rounds, include_process=include_process)
                if suggestions:
                    step1_prompt += f"\n\n【最终修正要求】\n{suggestions}"
                continue

    return final_payload, trace


def _normalize_payload(
    payload: Dict[str, Any],
    item: Dict[str, Any],
    question_type_key: str,
    question_index: int = 0,
) -> Dict[str, Any]:
    """对齐 qa_make 的字段与顺序，保证输出一致性。"""
    image_id = str(item.get("id", "unknown"))
    image_path = item.get("image_path")
    image_type = item.get("image_type")
    image_type = image_type if image_type not in (None, "all") else question_type_key and item.get("type") or "mixed"

    qt_cn = QUESTION_TYPES.get(question_type_key, payload.get("question_type", "问答题"))
    question_id = payload.get("question_id") or f"{image_id}_{question_type_key}_{question_index}"

    normalized = {
        "image_id": image_id,
        "image_path": image_path,
        "image_type": image_type or "mixed",
        "question_id": question_id,
        "question_type": qt_cn,
        "question": payload.get("question", ""),
        "options": payload.get("options"),
        "answer": payload.get("answer", ""),
    }

    if GLOBAL_CONFIG.get("include_process", True) and payload.get("qa_make_process"):
        normalized["qa_make_process"] = payload.get("qa_make_process")

    return normalized


def _load_input(path: str) -> List[Dict[str, Any]]:
    if path.lower().endswith(".jsonl"):
        data = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data.append(json.loads(line))
        return data
    with open(path, "r", encoding="utf-8") as f:
        obj = json.load(f)
    if isinstance(obj, dict) and "items" in obj:
        return obj["items"]
    if isinstance(obj, list):
        return obj
    raise ValueError("输入 JSON 格式不正确，需为数组或包含 items 字段的对象")


def _write_jsonl(path: str, item: Dict[str, Any]) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description="对抗式出题（A/B 找茬）")
    parser.add_argument("--input", required=True, help="输入JSON/JSONL")
    parser.add_argument("--output", required=True, help="输出JSONL")
    parser.add_argument("--image_type", default="mixed")
    parser.add_argument("--question_type", default="essay")
    parser.add_argument("--num", type=int, default=1, help="每张图生成题目数量（兼容 qa_make，仅取1）")
    parser.add_argument("--workers", type=int, default=1, help="兼容参数，占位")
    parser.add_argument("--batch", type=int, default=10, help="兼容参数，占位")
    parser.add_argument("--log_dir", type=str, default="./logs", help="兼容参数，占位")
    parser.add_argument("--log_mode", type=str, default="simple", choices=["simple", "detailed"], help="兼容参数，占位")
    parser.add_argument("--resume", action="store_true", help="断点续传：不清空已存在的输出文件")
    parser.add_argument("--max_rounds", type=int, default=3, help="A/B 找茬迭代轮数上限")
    parser.add_argument("--rounds", type=int, default=GLOBAL_CONFIG["rounds"])
    parser.add_argument("--api_base", default="https://dashscope.aliyuncs.com/compatible-mode/v1")
    parser.add_argument("--api_key", default="EMPTY")
    parser.add_argument("--model", default="qwen3-vl-plus")
    parser.add_argument("--temp", type=float, default=GLOBAL_CONFIG["temperature"])
    parser.add_argument("--tokens", type=int, default=GLOBAL_CONFIG["max_tokens"])
    parser.add_argument("--timeout", type=float, default=GLOBAL_CONFIG["request_timeout"])
    parser.add_argument("--retries", type=int, default=GLOBAL_CONFIG["max_retries"])
    parser.add_argument("--retry_sleep", type=float, default=GLOBAL_CONFIG["retry_sleep"])
    parser.add_argument("--enable_thinking", action="store_true")
    parser.add_argument("--no_process", action="store_true")
    parser.add_argument("--emit_trace", action="store_true", help="是否将trace也写入输出文件")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--random", action="store_true")
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()

    # 注入配置
    GLOBAL_CONFIG["api_base"] = args.api_base
    GLOBAL_CONFIG["api_key"] = args.api_key
    GLOBAL_CONFIG["model_name"] = args.model
    GLOBAL_CONFIG["temperature"] = args.temp
    GLOBAL_CONFIG["max_tokens"] = args.tokens
    GLOBAL_CONFIG["request_timeout"] = args.timeout
    GLOBAL_CONFIG["max_retries"] = args.retries
    GLOBAL_CONFIG["retry_sleep"] = args.retry_sleep
    GLOBAL_CONFIG["enable_thinking"] = args.enable_thinking
    GLOBAL_CONFIG["include_process"] = not args.no_process
    GLOBAL_CONFIG["rounds"] = args.rounds
    GLOBAL_CONFIG["questions_per_image"] = max(1, args.num)

    items = _load_input(args.input)

    if args.seed is not None:
        random.seed(args.seed)
    if args.random:
        random.shuffle(items)
    if args.limit is not None:
        items = items[: args.limit]

    # 保证输出目录存在
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    if os.path.exists(args.output) and not args.resume:
        open(args.output, "w", encoding="utf-8").close()

    for idx, item in enumerate(items, 1):
        final_payload, trace = generate_adversarial_qa(
            item,
            image_type=args.image_type,
            question_type=args.question_type,
            max_rounds=args.max_rounds,
        )
        if not final_payload:
            print(f"❌ image_id={item.get('id','unknown')} 生成失败")
            continue

        normalized = _normalize_payload(final_payload, item, args.question_type, question_index=0)
        _write_jsonl(args.output, normalized)
        print(f"✅ [{idx}/{len(items)}] image_id={item.get('id','unknown')} 已写入")

        if args.emit_trace:
            _write_jsonl(args.output, {"trace_image_id": item.get("id"), "trace": trace})


if __name__ == "__main__":
    main()


__all__ = ["generate_adversarial_qa"]

