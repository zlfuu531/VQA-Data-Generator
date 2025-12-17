"""
模型API调用模块
支持调用各种视觉语言模型的API
"""
import os
import sys
import base64
import time
import logging
import re
import json
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openai import OpenAI
try:
    from .config import API_CONFIG, EVAL_CONFIG
except ImportError:
    from config import API_CONFIG, EVAL_CONFIG


def encode_image(image_path: str) -> str:
    """
    将图片编码为 base64
    
    Args:
        image_path: 图片路径
        
    Returns:
        base64 编码的图片字符串
    """
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


def get_image_format(image_path: str) -> str:
    """
    获取图片格式（用于 data URI）
    
    Args:
        image_path: 图片路径
        
    Returns:
        图片格式（如 jpeg, png）
    """
    suffix = Path(image_path).suffix.lower().replace('.', '')
    if suffix == 'jpg':
        return 'jpeg'
    return suffix if suffix in ['jpeg', 'png', 'webp', 'gif'] else 'jpeg'


def call_model_api(
    model_name: str,
    prompt: str = None,
    image_paths: Optional[List[str]] = None,
    max_retries: Optional[int] = None,
    retry_delay: Optional[float] = None,
    messages: Optional[List[Dict[str, Any]]] = None
) -> Tuple[str, float, Dict[str, Any]]:
    """
    调用模型API
    
    Args:
        model_name: 模型名称（对应 API_CONFIG 中的 key）
        prompt: 提示词（如果提供了 messages，则忽略此参数）
        image_paths: 图片路径列表（可选，仅在未提供 messages 时使用）
        max_retries: 最大重试次数（默认使用配置）
        retry_delay: 重试延迟（默认使用配置）
        messages: 对话历史消息列表（可选，格式：[{"role": "user", "content": ...}, {"role": "assistant", "content": ...}, ...]）
                 如果提供了 messages，将使用它而不是 prompt 和 image_paths
        
    Returns:
        (answer, response_time, raw_response)
        - answer: 模型回答
        - response_time: 响应时间（秒）
        - raw_response: 原始API响应（字典格式）
    """
    if model_name not in API_CONFIG:
        raise ValueError(f"模型 '{model_name}' 不在 API_CONFIG 中")
    
    api_config = API_CONFIG[model_name]
    max_retries = max_retries or EVAL_CONFIG.get("max_retries", 3)
    retry_delay = retry_delay or EVAL_CONFIG.get("retry_delay", 1)
    
    client = OpenAI(
        base_url=api_config["base_url"],
        api_key=api_config["api_key"]
    )
    
    # 如果提供了 messages，直接使用；否则构建单条消息
    if messages is not None:
        # 使用提供的对话历史
        # 如果第一条消息是 user 且包含图片，需要确保图片格式正确
        if messages and len(messages) > 0:
            first_msg = messages[0]
            if first_msg.get("role") == "user" and image_paths:
                # 如果第一条消息是 user 且有图片，需要将图片添加到第一条消息中
                user_content = first_msg.get("content", [])
                if isinstance(user_content, str):
                    user_content = [{"type": "text", "text": user_content}]
                elif not isinstance(user_content, list):
                    user_content = []
                
                # 添加图片到第一条消息
                for image_path in image_paths:
                    if image_path.startswith(("http://", "https://")):
                        user_content.append({
                            "type": "image_url",
                            "image_url": {"url": image_path}
                        })
                    elif os.path.exists(image_path):
                        image_format = get_image_format(image_path)
                        base64_image = encode_image(image_path)
                        user_content.append({
                            "type": "image_url",
                            "image_url": {"url": f"data:image/{image_format};base64,{base64_image}"}
                        })
                    else:
                        logging.warning(f"图片文件不存在或URL无效: {image_path}")
                        continue
                
                messages[0]["content"] = user_content
    else:
        # 构建单条消息（原有逻辑）
        if prompt is None:
            raise ValueError("必须提供 prompt 或 messages 参数")
        
        user_content = []
        
        # 添加图片
        if image_paths:
            for image_path in image_paths:
                # 判断是URL还是本地路径
                if image_path.startswith(("http://", "https://")):
                    # URL格式，直接使用
                    user_content.append({
                        "type": "image_url",
                        "image_url": {"url": image_path}
                    })
                elif os.path.exists(image_path):
                    # 本地文件，编码为base64
                    image_format = get_image_format(image_path)
                    base64_image = encode_image(image_path)
                    user_content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/{image_format};base64,{base64_image}"}
                    })
                else:
                    logging.warning(f"图片文件不存在或URL无效: {image_path}")
                    continue
        
        # 添加文本提示词
        user_content.append({"type": "text", "text": prompt})
        
        messages = [{"role": "user", "content": user_content}]
    
    # 构建API调用参数
    # 超时时间：优先使用 EVAL_CONFIG 中的 timeout，其次使用模型配置中的 timeout
    timeout = EVAL_CONFIG.get("timeout") or api_config.get("timeout", 600)

    api_params = {
        "model": api_config["model"],
        "messages": messages,
        "max_tokens": api_config.get("max_tokens", 8192),
        "timeout": timeout,
    }

    # 可选参数：只在 config 中存在时才添加（与 module2 保持一致风格）
    if "temperature" in api_config:
        api_params["temperature"] = api_config["temperature"]
    if "top_p" in api_config:
        api_params["top_p"] = api_config["top_p"]
    if "frequency_penalty" in api_config:
        api_params["frequency_penalty"] = api_config["frequency_penalty"]
    if "presence_penalty" in api_config:
        api_params["presence_penalty"] = api_config["presence_penalty"]
    if "stream" in api_config:
        api_params["stream"] = api_config["stream"]

    # 处理 extra_body（某些API的特殊参数，比如思考模式 enable_thinking 等）
    # 在 config 中，我们已经把所有「非标准顶层参数」自动合并进了 extra_body，
    # 这里直接整体透传即可，兼容单轮 / 多轮。
    extra_body = api_config.get("extra_body", {})
    if extra_body:
        api_params["extra_body"] = extra_body
    
    # 重试机制
    last_error = None
    for attempt in range(max_retries):
        try:
            start_time = time.time()
            response = client.chat.completions.create(**api_params)
            response_time = time.time() - start_time
            
            if not response.choices or len(response.choices) == 0:
                raise ValueError("API响应中没有choices字段")
            
            answer = response.choices[0].message.content
            if not answer:
                raise ValueError("API响应内容为空")
            
            # 保存完整的原始响应（用于详细日志）
            try:
                if hasattr(response, "model_dump"):
                    raw_response = response.model_dump()
                elif isinstance(response, dict):
                    raw_response = response
                else:
                    # 手动构建完整响应字典
                    raw_response = {
                        "id": getattr(response, "id", None),
                        "object": getattr(response, "object", None),
                        "created": getattr(response, "created", None),
                        "model": getattr(response, "model", None),
                        "usage": {
                            "prompt_tokens": response.usage.prompt_tokens if hasattr(response, 'usage') and response.usage else None,
                            "completion_tokens": response.usage.completion_tokens if hasattr(response, 'usage') and response.usage else None,
                            "total_tokens": response.usage.total_tokens if hasattr(response, 'usage') and response.usage else None,
                        } if hasattr(response, 'usage') and response.usage else None,
                    }
                    if hasattr(response, "choices") and len(response.choices) > 0:
                        choice = response.choices[0]
                        choice_dict = {
                            "index": getattr(choice, "index", None),
                            "finish_reason": getattr(choice, "finish_reason", None),
                        }
                        if hasattr(choice, "message"):
                            message = choice.message
                            message_dict = {
                                "role": getattr(message, "role", None),
                                "content": getattr(message, "content", None),
                            }
                            # 详细日志模式下：保留所有reasoning字段，不按优先级过滤
                            # 这样详细日志可以显示所有思考内容
                            if hasattr(message, "reasoning") and getattr(message, "reasoning", None):
                                message_dict["reasoning"] = getattr(message, "reasoning")
                            if hasattr(message, "reasoning_content") and getattr(message, "reasoning_content", None):
                                message_dict["reasoning_content"] = getattr(message, "reasoning_content")
                            if hasattr(message, "reasoning_details") and getattr(message, "reasoning_details", None):
                                message_dict["reasoning_details"] = getattr(message, "reasoning_details")
                            choice_dict["message"] = message_dict
                        raw_response["choices"] = [choice_dict]
            except Exception as e:
                logging.warning(f"无法序列化完整响应对象: {e}")
                # 降级：只保存基本信息
                raw_response = {
                    "model": response.model if hasattr(response, 'model') else None,
                    "usage": {
                        "prompt_tokens": response.usage.prompt_tokens if hasattr(response, 'usage') and response.usage else None,
                        "completion_tokens": response.usage.completion_tokens if hasattr(response, 'usage') and response.usage else None,
                        "total_tokens": response.usage.total_tokens if hasattr(response, 'usage') and response.usage else None,
                    } if hasattr(response, 'usage') and response.usage else None
                }
            
            return answer, response_time, raw_response
            
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                wait_time = retry_delay * (2 ** attempt)  # 指数退避
                logging.warning(f"API调用失败（尝试 {attempt + 1}/{max_retries}）: {e}，{wait_time:.1f}秒后重试...")
                time.sleep(wait_time)
            else:
                logging.error(f"API调用失败（已重试 {max_retries} 次）: {e}")
                raise
    
    # 如果所有重试都失败
    raise Exception(f"API调用失败: {last_error}")


def extract_boxed_content(text: str) -> Optional[str]:
    """
    从文本中提取 \\boxed{} 中的内容，支持嵌套大括号
    
    Args:
        text: 输入文本
        
    Returns:
        提取的内容，如果未找到则返回 None
    """
    # 手动查找所有 \\boxed{ ... } 配对，支持嵌套大括号
    all_matches = []
    pos = 0
    
    while True:
        # 查找下一个 \\boxed{
        start_idx = text.find('\\boxed{', pos)
        if start_idx == -1:
            break
        
        # 从 \\boxed{ 后面开始匹配大括号
        brace_start = start_idx + len('\\boxed{')
        depth = 0
        end_idx = -1
        
        for i in range(brace_start, len(text)):
            if text[i] == '{':
                depth += 1
            elif text[i] == '}':
                if depth == 0:
                    # 找到匹配的右大括号
                    end_idx = i
                    break
                else:
                    depth -= 1
        
        if end_idx != -1:
            # 提取内容
            content = text[brace_start:end_idx].strip()
            if content:
                all_matches.append(content)
            pos = end_idx + 1
        else:
            # 未找到匹配的右大括号，跳过这个 \\boxed{
            pos = brace_start
    
    # 返回最后一个匹配（通常是最终答案）
    return all_matches[-1] if all_matches else None


def extract_json_from_text(text: str) -> Dict[str, Any]:
    """
    从文本中提取JSON对象（参考 model1.py）
    
    Args:
        text: 输入文本
        
    Returns:
        提取的JSON字典，如果未找到则返回空字典
    """
    text = text.strip()
    # 尝试匹配 ```json {...} ``` 或 {...}
    pattern = r"```json\s*(\{.*?\})\s*```|(\{.*\})"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        json_str = match.group(1) or match.group(2)
        try:
            return json.loads(json_str)
        except:
            pass
    
    # 如果没找到代码块，尝试直接寻找JSON
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1:
        try:
            return json.loads(text[start:end+1])
        except:
            pass
    
    return {}


def extract_answer_by_keywords(text: str) -> Optional[str]:
    """
    通过关键词模式提取答案（参考 model1.py）
    
    Args:
        text: 输入文本
        
    Returns:
        提取的答案，如果未找到则返回 None
    """
    # 查找 "答案是"、"答案："、"Answer:" 等关键词后的内容
    answer_patterns = [
        r'答案是[：:]\s*(.+?)(?:\n|$)',
        r'答案[：:]\s*(.+?)(?:\n|$)',
        r'Answer[：:]\s*(.+?)(?:\n|$)',
        r'最终答案[：:]\s*(.+?)(?:\n|$)',
        r'答案为[：:]\s*(.+?)(?:\n|$)',
        r'答案是\s*(.+?)(?:\n|$)',
    ]
    for pattern in answer_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            answer_content = match.group(1).strip()
            # 清理可能的标点符号
            answer_content = answer_content.rstrip('。，,')
            if answer_content:
                return answer_content
    return None


def extract_answer_from_response(response: str, has_options: bool = False) -> tuple:
    """
    从模型响应中提取答案（参考 model1.py 的多层 fallback 机制）
    
    提取策略（按优先级）：
    1. 从 \\boxed{} 中提取（支持嵌套大括号）
    2. 从 JSON 格式中提取（兼容旧格式）
    3. 通过关键词模式提取（"答案是"、"答案："等）
    4. 如果都没有，返回完整响应（保底机制）
    
    Args:
        response: 模型原始响应
        has_options: 是否是选择题（保留参数以兼容现有调用，但不再使用）
        
    Returns:
        (extracted_answer, is_from_box, original_response)
        - extracted_answer: 提取的答案
        - is_from_box: 是否从 \\boxed{} 中提取（True表示从box中提取，False表示使用完整响应）
        - original_response: 原始完整响应（用于fallback）
    """
    original_response = response.strip()
    response = original_response
    
    # ==================== 策略1: 从 \\boxed{} 中提取（支持嵌套大括号） ====================
    boxed_content = extract_boxed_content(response)
    if boxed_content:
        # 从 box 中成功提取到内容
        logging.debug(f"从 \\boxed{{}} 中提取到答案: {boxed_content[:100]}")
        return boxed_content, True, original_response
    
    # ==================== 策略2: 从 JSON 格式中提取（兼容旧格式） ====================
    result_json = extract_json_from_text(response)
    if result_json:
        answer_wrapped = result_json.get("answer", "")
        if answer_wrapped:
            # 尝试从 JSON 的 answer 字段中提取 boxed 格式
            answer_from_json_box = extract_boxed_content(answer_wrapped)
            if answer_from_json_box:
                logging.debug(f"从 JSON 格式的 \\boxed{{}} 中提取到答案: {answer_from_json_box[:100]}")
                return answer_from_json_box, True, original_response
            else:
                # 如果没有 boxed 格式，直接使用 answer 内容
                answer_cleaned = answer_wrapped.strip()
                if answer_cleaned:
                    logging.debug(f"从 JSON 格式中提取到答案: {answer_cleaned[:100]}")
                    return answer_cleaned, False, original_response
    
    # ==================== 策略3: 通过关键词模式提取 ====================
    answer_from_keywords = extract_answer_by_keywords(response)
    if answer_from_keywords:
        logging.debug(f"通过关键词模式提取到答案: {answer_from_keywords[:100]}")
        return answer_from_keywords, False, original_response
    
    # ==================== 策略4: 如果都没有提取到，返回完整响应（保底机制） ====================
    logging.debug("未能从任何策略中提取到答案，使用完整响应作为保底")
    return original_response, False, original_response
