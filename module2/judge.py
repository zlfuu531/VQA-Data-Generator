"""
评判模块 (Refactored)
使用评判模型来判断模型答案与GT是否一致，采用 JSON 结构化输出以确保解析准确性。
"""
import os
import sys
import base64
import time
import json
import re
from typing import Optional, Tuple

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openai import OpenAI
from module2.config import API_CONFIG, MODEL_CONFIG
from utils import compare_answers  # 假设这是你的兜底字符串比较函数

def clean_json_text(text: str) -> str:
    """
    从模型输出中提取 JSON 字符串。
    兼容模型输出 ```json ... ``` 包裹的情况。
    """
    text = text.strip()
    # 尝试匹配 ```json {...} ``` 或 {...}
    pattern = r"```json\s*(\{.*?\})\s*```|(\{.*\})"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        # 获取匹配到的第一个非空组
        return match.group(1) or match.group(2)
    
    # 如果没找到代码块，尝试直接寻找左右大括号包裹的内容
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1:
        return text[start:end+1]
    
    return text

def judge_answer_with_model(model_answer: str, gt_answer: str, question: str, 
                            image_path: Optional[str] = None, options: Optional[dict] = None) -> Tuple[bool, str, float, Optional[dict], str]:
    """
    使用评判模型判断模型答案与GT是否一致
    
    Returns:
        (is_match, reasoning, response_time, raw_response_json, final_prompt)
        - is_match: 是否匹配
        - reasoning: 评判理由
        - response_time: 响应时间（秒）
        - raw_response_json: 原始API响应（字典格式）
        - final_prompt: 最终提交给模型的完整提示词（用于日志记录）
    """
    start_time = time.time()
    
    try:
        # --- 1. 配置加载 ---
        judge_model_name = MODEL_CONFIG.get("judge_model")
        if not judge_model_name:
            raise ValueError("MODEL_CONFIG 中未配置 'judge_model' 字段")
        
        if judge_model_name not in API_CONFIG:
            raise ValueError(
                f"judge_model 配置 '{judge_model_name}' 在 API_CONFIG 中不存在。"
                f"可用的配置: {list(API_CONFIG.keys())}"
            )
        
        api_config = API_CONFIG[judge_model_name]
        
        # 验证必要的配置字段
        required_fields = ["base_url", "api_key", "model"]
        missing_fields = [f for f in required_fields if not api_config.get(f)]
        if missing_fields:
            raise ValueError(
                f"judge_model 配置 '{judge_model_name}' 缺少必要字段: {missing_fields}"
            )
        
        client = OpenAI(
            base_url=api_config["base_url"],
            api_key=api_config["api_key"]
        )
        model_name = api_config["model"]
        
        # --- 2. 构建结构化提示词 (System Prompt + User Prompt) ---
        # 核心指令：定义评判标准和输出格式
        system_prompt = """你是一个严格且智能的答案评判系统。你的任务是判断[模型输出]与[标准答案]在语义上是否一致。

请遵循以下评判标准：
1. **语义优先**：如果含义相同但表达方式不同（例如"10.5"与"10.50"，"北京"与"中国北京"），应判定为 True。
2. **忽略格式**：忽略标点符号、Markdown格式、大小写的差异。
3. **关键信息**：如果题目要求计算数值，数值必须准确；如果要求解释，核心逻辑必须一致。
4. **多选答案**：如果标准答案包含多个结果（例如多选题目或者多个问题），模型答案必须包含所有正确答案且一一对应正确才算正确。部分正确应判定为 False。

⚠️ **输出格式要求**：
请仅输出一个标准的 JSON 对象，不要包含任何其他解释性文字或Markdown标记。格式如下：
{
    "result": true,  // 如果一致为 true，不一致为 false
    "reasoning": "这里写简短的判定理由"
}
"""

        user_content_text = f"""
[问题]
{question}
"""
        
        # 如果存在选项，添加到提示词中
        if options is not None and isinstance(options, dict) and options:
            opt_str = "；".join([f"{k}: {v}" for k, v in options.items()])
            user_content_text += f"""
[选项]
{opt_str}
"""
        
        user_content_text += f"""
[标准答案 (GT)]
{gt_answer}

[模型答案]
{model_answer}

注意：只需要比较答案部分，不需要考虑思考过程（process）。

请根据上述内容生成 JSON 评判结果。
"""

        # --- 3. 构建消息体 ---
        messages = [{"role": "system", "content": system_prompt}]
        
        user_message_content = []
        user_message_content.append({"type": "text", "text": user_content_text})

        # 处理图片
        #是否输入图片！！！！！！！
        
        # ================== 修改开始：注释掉图片处理 ==================
        # 处理图片
        # if image_path and os.path.exists(image_path):
        #     with open(image_path, "rb") as image_file:
        #         base64_image = base64.b64encode(image_file.read()).decode('utf-8')
        #     user_message_content.append({
        #         "type": "image_url",
        #         "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
        #     })
        # ================== 修改结束 ==================
        
        messages.append({"role": "user", "content": user_message_content})




        

        # --- 4. 调用 API ---
        print(f"      [评判模型] ({model_name}) 开始判断...")
        
        # 构建API调用参数
        api_params = {
            "model": model_name,
            "messages": messages,
            "max_tokens": api_config.get("max_tokens", 512),
            "timeout": api_config.get("timeout", 120)
        }
        # 仅当显式配置了温度时才传递，避免覆盖模型默认值
        if api_config.get("temperature") is not None:
            api_params["temperature"] = api_config["temperature"]
        
        # 如果模型支持JSON模式，添加该参数（某些模型可能不支持）
        try:
            response = client.chat.completions.create(
                **api_params,
                response_format={"type": "json_object"}
            )
        except Exception as json_format_error:
            # 如果JSON模式不支持，回退到普通模式
            print(f"      [评判模型] ⚠️ JSON模式不支持，使用普通模式: {json_format_error}")
            response = client.chat.completions.create(**api_params)

        # --- 5. 保存原始响应JSON ---
        raw_response_json = None
        try:
            # 将响应对象转换为字典格式
            if hasattr(response, 'model_dump'):
                raw_response_json = response.model_dump()
            elif hasattr(response, 'dict'):
                raw_response_json = response.dict()
            else:
                # 手动构建响应字典
                raw_response_json = {
                    "id": getattr(response, 'id', None),
                    "object": getattr(response, 'object', None),
                    "created": getattr(response, 'created', None),
                    "model": getattr(response, 'model', None),
                    "choices": []
                }
                if hasattr(response, 'choices') and response.choices:
                    for choice in response.choices:
                        choice_dict = {
                            "index": getattr(choice, 'index', None),
                            "finish_reason": getattr(choice, 'finish_reason', None),
                            "message": {}
                        }
                        if hasattr(choice, 'message'):
                            msg = choice.message
                            choice_dict["message"] = {
                                "role": getattr(msg, 'role', None),
                                "content": getattr(msg, 'content', None),
                            }
                        raw_response_json["choices"].append(choice_dict)
        except Exception as e:
            print(f"      [评判模型] ⚠️ 警告：无法序列化原始响应: {e}")
            raw_response_json = None
        
        # --- 6. 构建最终提示词（用于日志记录） ---
        final_prompt = f"{system_prompt}\n\n{user_content_text}"
        
        # --- 7. 解析结果 ---
        if not response.choices or len(response.choices) == 0:
            raise ValueError("API响应中没有choices字段")
        
        raw_content = response.choices[0].message.content
        if not raw_content:
            raise ValueError("API响应内容为空")
        
        cleaned_content = clean_json_text(raw_content)
        
        try:
            result_json = json.loads(cleaned_content)
            is_match = bool(result_json.get("result", False)) # 默认为 False 以防万一
            reasoning = result_json.get("reasoning", "未提供理由") or "未提供理由"
        except json.JSONDecodeError as e:
            # 如果JSON解析失败，记录日志并回退到规则匹配（防止程序崩溃）
            print(f"      [评判模型] ⚠️ JSON解析失败: {e}")
            print(f"      [评判模型] 原始内容（前200字符）: {raw_content[:200]}...")
            reasoning = f"JSON解析错误: {str(e)}"
            # 降级策略：简单的关键词匹配
            content_lower = raw_content.lower()
            # 查找明确的true/false标记
            if '"result": true' in content_lower or '"result":true' in content_lower:
                is_match = True
            elif '"result": false' in content_lower or '"result":false' in content_lower:
                is_match = False
            else:
                # 最后的倔强：查找true/false关键词
                is_match = "true" in content_lower and "false" not in content_lower

        response_time = time.time() - start_time
        
        status_icon = "✅" if is_match else "❌"
        print(f"      [评判模型] {status_icon} 结果: {'一致' if is_match else '不一致'} | 耗时: {response_time:.2f}s | 理由: {reasoning[:50]}...")
        
        return is_match, reasoning, response_time, raw_response_json, final_prompt

    except Exception as e:
        error_msg = f"评判过程发生异常: {str(e)}"
        response_time = time.time() - start_time
        print(f"      [评判模型] 🚨 异常: {error_msg}")
        
        # 降级策略：使用基于规则的字符串比较
        print("      [评判模型] 🔄 降级为字符串精确匹配...")
        is_match = compare_answers(model_answer, gt_answer)
        # 构建最终提示词（即使失败也记录）
        final_prompt = f"{system_prompt}\n\n{user_content_text}" if 'system_prompt' in locals() and 'user_content_text' in locals() else ""
        return is_match, f"模型评判失败({str(e)})，已转为规则匹配", response_time, None, final_prompt