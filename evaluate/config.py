"""
评测框架配置文件
支持API配置、模型配置、评测参数等
"""
import os
import logging
from typing import Dict, Any, Optional, List

# 自动加载 .env 文件（如果存在 python-dotenv）
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))
except ImportError:
    pass


def _get_env(key: str, default: str = "") -> str:
    """从环境变量读取配置，提供默认值"""
    return os.getenv(key, default)



# ==================== API 服务商配置 ====================
BASE_URL_CONFIG = {
    "volces": {  # 火山引擎
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "api_key": _get_env("api2"),
    },
    "siliconflow": {  # SiliconFlow
        "base_url": "https://api.siliconflow.cn/v1",
        "api_key": _get_env("api4"),
    },
    "dashscope": {  # 阿里云 DashScope
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key": _get_env("api1"),
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "api_key": _get_env("api3"),
    }
}

# ==================== 模型定义配置 ====================
MODEL_DEFINITIONS = {
    "doubao-seed-1-6-251015": {
        "base_url_key": "volces",
        "model": "doubao-seed-1-6-251015",
        "max_tokens": 8192,
        "timeout": 600,
        "enable_thinking": True,
        "extra_body": {}
    },
    "GLM-4.6V": {
        "base_url_key": "openrouter",
        "model": "z-ai/GLM-4.6V",
        "max_tokens": 8192,
        "timeout": 600,
        "enable_thinking": False,
        "extra_body": {}
    },
    "qwen-vl-max": {
        "base_url_key": "dashscope",
        "model": "qwen-vl-max",
        "max_tokens": 8192,
        "timeout": 600,
        "stream": False,
        "enable_thinking": False,
        "extra_body": {}
    },
    "qwen-max": {  # 裁判模型
        "base_url_key": "dashscope",
        "model": "qwen-max",
        "max_tokens": 1024,  
        "temperature": 0.01,
        "timeout": 600,
        "enable_thinking": False,
        "extra_body": {}
    }
    #可以添加评测的模型
}

# ==================== 评测模型配置 ====================
# 从环境变量读取要评测的模型列表
# 环境变量 EVAL_MODELS：逗号分隔的模型名称列表，如 "doubao,GLM,qwenvlmax"
# 模型名称必须对应 MODEL_DEFINITIONS 中的 key
def get_eval_models() -> List[str]:
    """
    获取要评测的模型列表
    
    Returns:
        模型名称列表（对应 MODEL_DEFINITIONS 中的 key）
    """
    eval_models_str = _get_env("EVAL_MODELS", "")
    if not eval_models_str:
        # 如果没有设置环境变量，返回空列表（需要在脚本中设置）
        return []
    
    # 解析逗号分隔的模型列表
    models = [m.strip() for m in eval_models_str.split(",") if m.strip()]
    
    # 验证模型是否在 MODEL_DEFINITIONS 中
    valid_models = []
    for model in models:
        if model in MODEL_DEFINITIONS:
            valid_models.append(model)
        else:
            # 使用 print 而不是 logging，因为 logging 可能还未初始化
            print(f"警告：模型 '{model}' 不在 MODEL_DEFINITIONS 中，已跳过")
    
    return valid_models

# ==================== 裁判模型配置 ====================
JUDGE_MODEL_CONFIG = {
    "name": "qwen-max",  # 指向 MODEL_DEFINITIONS 中的 key
    "enabled": True
}

# ==================== 用户画像配置 ====================
# 三种用户画像：beginner（小白）、retail（散户）、expert（专家）
USER_PROFILES = ["beginner", "retail", "expert"]

# ==================== 评测参数配置 ====================
# 支持从环境变量读取配置（优先级：环境变量 > 默认值）
def _get_int_env(key: str, default: int) -> int:
    """从环境变量读取整数配置"""
    value = _get_env(key, "")
    return int(value) if value and value.isdigit() else default

def _get_float_env(key: str, default: float) -> float:
    """从环境变量读取浮点数配置"""
    value = _get_env(key, "")
    try:
        return float(value) if value else default
    except ValueError:
        return default

EVAL_CONFIG = {
    "max_retries": _get_int_env("EVAL_MAX_RETRIES", 3),  # API调用最大重试次数
    "retry_delay": _get_float_env("EVAL_RETRY_SLEEP", 1.0),  # 重试延迟（秒）
    "judge_max_retries": _get_int_env("EVAL_JUDGE_MAX_RETRIES", 3),  # 裁判模型最大重试次数
    "judge_retry_delay": _get_float_env("EVAL_JUDGE_RETRY_DELAY", 1.0),  # 裁判模型重试延迟（秒）
    "save_intermediate": True,  # 是否保存中间结果（断点续跑）
    "output_format": _get_env("EVAL_OUTPUT_FORMAT", "json"),  # 输出格式：json 或 jsonl
    "timeout": _get_int_env("EVAL_TIMEOUT", 600),  # API超时时间（秒）
    "batch_size": _get_int_env("EVAL_BATCH_SIZE", 10),  # JSON格式批量写入大小
}

# ==================== 动态生成 API_CONFIG ====================
API_CONFIG = {}
for model_key, model_def in MODEL_DEFINITIONS.items():
    base_url_key = model_def.get("base_url_key")
    if base_url_key not in BASE_URL_CONFIG:
        raise ValueError(
            f"模型 '{model_key}' 的 base_url_key '{base_url_key}' 在 BASE_URL_CONFIG 中不存在。"
        )
    
    base_url_config = BASE_URL_CONFIG[base_url_key]
    API_CONFIG[model_key] = {
        "base_url": base_url_config["base_url"],
        "api_key": base_url_config["api_key"],
        "model": model_def["model"],
        "max_tokens": model_def.get("max_tokens", 8192),
        "timeout": model_def.get("timeout", 600),
        "enable_thinking": model_def.get("enable_thinking", False),
        "extra_body": model_def.get("extra_body", {}),
    }
    # 可选参数
    if "temperature" in model_def:
        API_CONFIG[model_key]["temperature"] = model_def["temperature"]
    if "stream" in model_def:
        API_CONFIG[model_key]["stream"] = model_def["stream"]



