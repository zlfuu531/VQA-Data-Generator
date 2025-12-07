"""
模型3 API调用
独立文件，可以直接调用
使用config.py中的model3配置
要求输出格式：answer用 \\boxed{} 格式括起来，process包含推理字段和除boxed外的其他内容
"""
import os
import sys
import base64
import time
import json
import re
from typing import Optional

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openai import OpenAI
from module2.config import API_CONFIG, MODEL_CONFIG
from utils import extract_answer_from_boxed


# ==================== 通用提示词模板（与其他模型保持完全一致） ====================
PROMPT_TEMPLATE = """你是一个高级AI助手，擅长视觉和文本理解。请仔细分析以下问题并按照指定格式输出。

问题：{question}

回答要求：
1. 深入理解问题的本质和背景
2. 系统性地分析问题的各个层面
3. 清晰地展示你的推理过程和思考路径
4. 给出准确、完整的最终答案

⚠️ **重要：最终答案必须用 \\boxed{{}} 格式括起来**

格式要求：
- **每次请求只返回一个 \\boxed{{}}，里面包含这次请求的所有答案**
- 如果这次请求包含多个问题或需要多个答案（如多选题），请将所有答案放在同一个 \\boxed{{}} 中，用逗号或分号分隔
- 格式示例：
  * 单个答案：\\boxed{{42}} 或 \\boxed{{这是答案}}
  * 多个答案（多选题）：\\boxed{{答案A, 答案B}} 或 \\boxed{{答案A; 答案B}}
  * 多个问题：\\boxed{{问题1答案, 问题2答案}} 或 \\boxed{{问题1答案; 问题2答案}}

注意：
- 推理过程可以包含任何你认为有用的思考步骤
- **最终答案必须用 \\boxed{{}} 包裹，这是必须的格式要求**
- 不要使用Markdown代码块格式
- 输出语言应与问题语言保持一致"""


def extract_json_from_text(text: str) -> dict:
    """从文本中提取JSON对象"""
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


def extract_answer_and_process(text: str) -> tuple:
    """
    从文本中提取答案和推理过程
    答案从 \\boxed{} 格式中提取
    process 包含推理字段和除 boxed 外的其他内容
    """
    # 首先尝试从 \\boxed{} 中提取答案
    answer = extract_answer_from_boxed(text)
    
    # 提取 process：移除 \\boxed{} 及其内容，保留其他所有内容
    # 需要正确处理嵌套大括号的情况
    process = text
    start_idx = process.find('\\boxed{')
    if start_idx != -1:
        # 找到匹配的右大括号
        brace_start = start_idx + len('\\boxed{')
        depth = 0
        end_idx = -1
        for i in range(brace_start, len(process)):
            if process[i] == '{':
                depth += 1
            elif process[i] == '}':
                if depth == 0:
                    end_idx = i
                    break
                depth -= 1
        
        if end_idx != -1:
            # 移除整个 \\boxed{...} 部分
            process = (process[:start_idx] + process[end_idx+1:]).strip()
        else:
            # 如果没有找到匹配的右大括号，只移除 \\boxed{ 部分
            process = process[:start_idx].strip()
    
    return process, answer


def call_model3_api(question: str, image_path: Optional[str] = None) -> list:
    """
    调用模型3 API回答问题
    
    Args:
        question: 问题文本
        image_path: 图片路径（可选）
    
    Returns:
        [process, answer, response_time]
        - process: 思考过程/推理过程
        - answer: 最终答案（已从answer_model3包裹中提取）
        - response_time: 响应时间（秒）
    """
    start_time = time.time()
    
    try:
        # 从配置获取API信息
        api_config_name = MODEL_CONFIG["model3"]["name"]
        api_config = API_CONFIG[api_config_name]
        
        # 初始化OpenAI客户端
        client = OpenAI(
            base_url=api_config["base_url"],
            api_key=api_config["api_key"]
        )
        model_name = api_config["model"]
        
        # ========== 构建提示词（与其他模型使用同一模板） ==========
        # 提示词拼接流程：
        # 1. question 参数来自 answer_comparison.py::get_model_answer() 或 get_model_answer_multi_round()
        # 2. 对于单轮题：question 是 model_evaluation.py::_build_model_question() 构建的完整问题文本
        # 3. 对于多轮题：question 是 get_model_answer_multi_round() 构造的 round_question（包含格式要求）
        # 4. 最终提示词 = PROMPT_TEMPLATE + question
        # 详见 module2/PROMPT_FLOW.md
        prompt = PROMPT_TEMPLATE.format(question=question)
        
        # ========== 构建消息 ==========
        if image_path and os.path.exists(image_path):
            # 有图片：编码图片
            with open(image_path, "rb") as image_file:
                base64_image = base64.b64encode(image_file.read()).decode('utf-8')
            
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ]
        else:
            # 无图片：纯文本
            messages = [{"role": "user", "content": prompt}]
        
        # ========== 调用API ==========
        print(f"[模型3] 开始调用API: {model_name}")
        print(f"[模型3] 问题: {question[:50]}...")
        
        # 构建 extra_body（合并 enable_thinking 和用户自定义的 extra_body）
        extra_body = api_config.get("extra_body", {}).copy()
        enable_thinking = api_config.get("enable_thinking", False)
        '''
        # 检查模型是否支持思考模式（只有 Qwen3 系列模型支持）
        model_name_lower = model_name.lower()
        supports_thinking = any(keyword in model_name_lower for keyword in ["qwen3", "qwen-3"])
        
        # 只有在模型支持且配置启用时才添加 enable_thinking
        if enable_thinking and supports_thinking:
            extra_body["enable_thinking"] = True
            print(f"[模型3] 启用思考模式（模型支持：{model_name}）")
        elif enable_thinking and not supports_thinking:
            print(f"[模型3] ⚠️ 警告：模型 {model_name} 可能不支持思考模式，已忽略 enable_thinking 配置")
        '''
        if enable_thinking:
            extra_body["enable_thinking"] = True
            print(f"[模型3] 已启用思考参数 (enable_thinking=True)")     
        # 构建API调用参数（只添加 config 中存在的参数）
        api_params = {
            "model": model_name,
            "messages": messages,
            "timeout": api_config.get("timeout", 300)  # timeout 是必需的
        }
        
        # 可选参数：只在 config 中存在时才添加
        if "temperature" in api_config:
            api_params["temperature"] = api_config["temperature"]
        if "max_tokens" in api_config:
            api_params["max_tokens"] = api_config["max_tokens"]
        if "top_p" in api_config:
            api_params["top_p"] = api_config["top_p"]
        if "frequency_penalty" in api_config:
            api_params["frequency_penalty"] = api_config["frequency_penalty"]
        if "presence_penalty" in api_config:
            api_params["presence_penalty"] = api_config["presence_penalty"]
        
        # 添加 extra_body（如果有）
        if extra_body:
            api_params["extra_body"] = extra_body
        
        # 判断是否使用流式输出
        use_stream = api_config.get("stream", False)
        if use_stream:
            api_params["stream"] = True
            print(f"[模型3] 使用流式输出模式")
        
        response = client.chat.completions.create(**api_params)
        
        # ========== 保存原始响应JSON ==========
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
                            "message": {}
                        }
                        if hasattr(choice, 'message'):
                            msg = choice.message
                            choice_dict["message"] = {
                                "role": getattr(msg, 'role', None),
                                "content": getattr(msg, 'content', None),
                                "reasoning_content": getattr(msg, 'reasoning_content', None) if hasattr(msg, 'reasoning_content') else None
                            }
                        raw_response_json["choices"].append(choice_dict)
        except Exception as e:
            print(f"[模型3] ⚠️ 警告：无法序列化原始响应: {e}")
            raw_response_json = None
        
        # ========== 解析响应 ==========
        process_content = ""
        answer_content = ""
        reasoning_content = ""  # 思考模式返回的推理内容
        full_content = ""  # 完整内容
        
        if use_stream:
            # 流式输出处理
            for chunk in response:
                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    if hasattr(delta, 'content') and delta.content:
                        full_content += delta.content
        else:
            # 非流式输出处理
            if response.choices and len(response.choices) > 0:
                message = response.choices[0].message
                full_content = message.content if hasattr(message, 'content') and message.content else ""
                
                # 检查是否有 reasoning_content（思考模式）
                if hasattr(message, 'reasoning_content') and message.reasoning_content:
                    reasoning_content = message.reasoning_content
                    print(f"[模型3] 检测到思考模式，reasoning_content长度: {len(reasoning_content)}")
        
        # 提取答案和推理过程
        if full_content:
            # 如果启用了思考模式且有 reasoning_content，合并到 process 中
            if reasoning_content:
                if process_content:
                    process_content = f"{reasoning_content}\n\n{process_content}"
                else:
                    process_content = reasoning_content
            
            # 从完整内容中提取答案和推理过程
            # answer 从 \\boxed{} 中提取
            # process 是除 boxed 外的其他所有内容
            process_from_extract, answer_content = extract_answer_and_process(full_content)
            
            # 合并 process
            if process_from_extract:
                if process_content:
                    process_content = f"{process_content}\n\n{process_from_extract}"
                else:
                    process_content = process_from_extract
            
            # 如果提取不到答案，尝试多种方式提取
            if not answer_content:
                # 方法1：尝试从JSON格式中提取（兼容旧格式）
                result_json = extract_json_from_text(full_content)
                if result_json:
                    process_from_json = result_json.get("process", "")
                    answer_wrapped = result_json.get("answer", "")
                    # 尝试从answer中提取boxed格式
                    answer_content = extract_answer_from_boxed(answer_wrapped)
                    if not answer_content:
                        # 如果没有boxed格式，直接使用answer内容
                        answer_content = answer_wrapped.strip()
                    
                    # 合并 process
                    if process_from_json:
                        if process_content:
                            process_content = f"{process_content}\n\n{process_from_json}"
                        else:
                            process_content = process_from_json
                
                # 方法2：尝试查找常见的答案格式（如果还是没有）
                if not answer_content:
                    # 查找 "答案是"、"答案："、"Answer:" 等关键词后的内容
                    answer_patterns = [
                        r'答案是[：:]\s*(.+?)(?:\n|$)',
                        r'答案[：:]\s*(.+?)(?:\n|$)',
                        r'Answer[：:]\s*(.+?)(?:\n|$)',
                        r'最终答案[：:]\s*(.+?)(?:\n|$)',
                    ]
                    for pattern in answer_patterns:
                        match = re.search(pattern, full_content, re.IGNORECASE)
                        if match:
                            answer_content = match.group(1).strip()
                            # 清理可能的标点符号
                            answer_content = answer_content.rstrip('。，,')
                            if answer_content:
                                print(f"[模型3] 从文本中提取到答案: {answer_content[:50]}")
                                break
            
            # 如果仍然没有答案，将全部内容作为process，答案为空
            if not answer_content:
                if not process_content:
                    process_content = full_content
                print(f"[模型3] ⚠️ 警告：未能提取到答案，请检查模型输出格式")
        
        response_time = time.time() - start_time
        
        print(f"[模型3] ✅ 调用完成，耗时: {response_time:.2f}秒")
        print(f"[模型3] process长度: {len(process_content)}, answer长度: {len(answer_content)}")
        
        # 返回格式: [process, answer, response_time, raw_response_json, final_prompt]
        # final_prompt: 最终提交给模型的完整提示词（用于日志记录）
        return [process_content, answer_content, response_time, raw_response_json, prompt]
        
    except Exception as e:
        error_msg = f"Exception: {str(e)}"
        response_time = time.time() - start_time
        print(f"[模型3] ❌ 调用失败: {error_msg}")
        import traceback
        traceback.print_exc()
        return ["", error_msg, response_time, None]


if __name__ == "__main__":
    # 测试代码
    test_question = "什么是深度学习？"
    print("=" * 60)
    print("测试模型3调用")
    print("=" * 60)
    result = call_model3_api(test_question)
    print(f"\n思考过程: {result[0][:100] if result[0] else '无'}...")
    print(f"答案: {result[1][:100] if result[1] else '无'}...")
    print(f"耗时: {result[2]:.2f}秒")
