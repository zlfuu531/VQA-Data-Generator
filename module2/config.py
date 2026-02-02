"""
配置文件：存储所有配置信息
。

📝 使用说明：
1. API 服务商配置（BASE_URL_CONFIG）：
   - 定义不同的 API 服务商的 base_url 和对应的 api_key
   - 可以配置多个服务商（如 volces、siliconflow、dashscope 等）
   - API Key 从环境变量读取，需要设定.env文件，或者直接在config.py中设置

2. 模型定义配置（MODEL_DEFINITIONS）：
   - 定义所有可用的模型配置，每个模型通过 "base_url_key" 引用一个服务商配置
   - 可以定义很多模型，但使用时只需要在 MODEL_CONFIG 中选择
   - 每个模型可以独立配置参数（temperature、max_tokens、timeout 等）

3. 模型启用配置（MODEL_CONFIG）：
   - 在这里选择要使用的模型，修改 "enabled": True/False 来启用/禁用
   - "name" 字段指向 MODEL_DEFINITIONS 中的某个 key
   - 可以配置多个模型，但实际使用时只启用需要的模型

4. 环境变量设置方式：
   - 方式1：在项目根目录创建 .env 文件，内容如：api1=your-key-1
   - 方式2：在 shell 中：export api1=your-key-1

💡 配置流程：
   BASE_URL_CONFIG（服务商） → MODEL_DEFINITIONS（模型定义） → API_CONFIG（自动生成） → MODEL_CONFIG（选择使用）
"""
import os
from pickle import FALSE

# 自动加载 .env 文件（如果存在 python-dotenv）
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))
except ImportError:
    pass  # 如果没有安装 python-dotenv，使用 export 方式


def _get_env(key: str, default: str = "") -> str:
    """
    从环境变量读取配置，提供默认值。
    单独封装主要是为了后续如果需要做日志/校验会更集中。
    """
    return os.getenv(key, default)


# ==================== API 服务商配置 ====================
# 定义不同的 API 服务商的 base_url 和对应的 api_key
# 可以配置多个服务商，然后在模型定义中引用
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

# ==================== 模型启用配置 ====================
# 在这里修改 "enabled": True/False 来启用/禁用模型
MODEL_CONFIG = {
    "model1": {
        "name": "doubao-seed-1-6-251015",  # 指向 API_CONFIG 中的某个 key
        "enabled": True    # ⬅️ 修改这里：True=启用, False=禁用
    },
    "model2": {
        "name": "GLM-4.6V",  # 指向 API_CONFIG 中的某个 key
        "enabled": True     # ⬅️ 修改这里：True=启用, False=禁用
    },
    "model3": {
        "name": "qwen-vl-max",  # 指向 API_CONFIG 中的某个 key
        "enabled": True    # ⬅️ 修改这里：True=启用, False=禁用
    },
    "judge_model": "qwen-max"  # 裁判模型（固定使用 ）
}

# ==================== 模型定义配置 ====================
# 定义所有可用的模型配置，每个模型引用一个 base_url 配置
# 可以定义很多模型，但使用时只需要在 MODEL_CONFIG 中选择
MODEL_DEFINITIONS = {
    "doubao-seed-1-6-251015": {  # 配置标识符，可以自定义为任何名称
        "base_url_key": "volces",  # 指向 BASE_URL_CONFIG 中的某个 key
        "model": "doubao-seed-1-6-251015",  # 模型名称
        # 模型调用参数（每个模型可以独立配置）
        # "temperature": 0.7,  # 温度参数，控制随机性
        "max_tokens": 8192,  # 最大token数
        # "top_p": 0.9,  # nucleus sampling参数
        # "frequency_penalty": 0.0,  # 频率惩罚
        # "presence_penalty": 0.0,  # 存在惩罚
        "timeout": 600,  # 超时时间（秒）
        # 流式输出配置
        # "stream": False,  # 是否使用流式输出（False=非流式，True=流式）
        # 思考模式配置（适用于 Qwen3、Qwen3-Omni-Flash、Qwen3-VL 模型）
        "enable_thinking": True,  # 是否开启思考模式（开启后，思考内容通过 reasoning_content 字段返回）
        # extra_body 配置（非 OpenAI 标准参数，通过此字段传递）
        # 注意：enable_thinking 会自动合并到 extra_body 中，无需手动设置
        "extra_body": {}  # 额外的API参数（可选，如 {"enable_thinking": True}）
    },
    "硅基流动GLM": {  # 配置标识符，可以自定义为任何名称
        "base_url_key": "siliconflow",  # 指向 BASE_URL_CONFIG 中的某个 key
        "model": "zai-org/GLM-4.5V",  # 模型名称
        # 模型调用参数（每个模型可以独立配置）
        # "temperature": 0.8,  # 温度参数，控制随机性
        "max_tokens": 8192,  # 最大token数
        # "top_p": 0.95,  # nucleus sampling参数
        # "frequency_penalty": 0.0,  # 频率惩罚
        # "presence_penalty": 0.0,  # 存在惩罚
        "timeout": 600,  # 超时时间（秒）
        # 流式输出配置
        # "stream": False,  # 是否使用流式输出（False=非流式，True=流式）
        # 思考模式配置（适用于 Qwen3、Qwen3-Omni-Flash、Qwen3-VL 模型）
        "enable_thinking": True,  # 是否开启思考模式（开启后，思考内容通过 reasoning_content 字段返回）
        # extra_body 配置（非 OpenAI 标准参数，通过此字段传递）
        "extra_body": {}  # 额外的API参数（可选，如 {"enable_thinking": True}）
    },
    "GLM-4.6V": {  # 配置标识符，可以自定义为任何名称
        "base_url_key": "openrouter",  # 指向 BASE_URL_CONFIG 中的某个 key
        "model": "z-ai/GLM-4.6V",  # 模型名称
        # 模型调用参数（每个模型可以独立配置）
        # "temperature": 0.8,  # 温度参数，控制随机性
        "max_tokens": 8192,  # 最大token数
        # "top_p": 0.95,  # nucleus sampling参数
        # "frequency_penalty": 0.0,  # 频率惩罚
        # "presence_penalty": 0.0,  # 存在惩罚
        "timeout": 600,  # 超时时间（秒）
        # 流式输出配置
        # "stream": False,  # 是否使用流式输出（False=非流式，True=流式）
        # 思考模式配置（适用于 Qwen3、Qwen3-Omni-Flash、Qwen3-VL 模型）
        "enable_thinking": True,  # 是否开启思考模式（开启后，思考内容通过 reasoning_content 字段返回）
        # extra_body 配置（非 OpenAI 标准参数，通过此字段传递）
        "extra_body": {}  # 额外的API参数（可选，如 {"enable_thinking": True}）
    },
    "qwen-vl-max": {  # 配置标识符，可以自定义为任何名称
        "base_url_key": "dashscope",  # 指向 BASE_URL_CONFIG 中的某个 key
        "model": "qwen-vl-max",  # 模型名称
        # 模型调用参数（每个模型可以独立配置）
        # "temperature": 0.6,  # 温度参数，控制随机性
        "max_tokens": 8192,  # 最大token数
        # "top_p": 0.9,  # nucleus sampling参数
        # "frequency_penalty": 0.0,  # 频率惩罚
        # "presence_penalty": 0.0,  # 存在惩罚
        "timeout": 600,  # 超时时间（秒）
        # 流式输出配置
        "stream": False,  # 是否使用流式输出（False=非流式，True=流式）
        # 思考模式配置（适用于 Qwen3、Qwen3-Omni-Flash、Qwen3-VL 模型）
        "enable_thinking": True,  # 是否开启思考模式（注意：qwen-vl-max 可能不支持）
        # extra_body 配置（非 OpenAI 标准参数，通过此字段传递）
        "extra_body": {}  # 额外的API参数（可选，如 {"enable_thinking": True}）
    },
    "qwen-max": {  # 配置标识符，可以自定义为任何名称（评判模型）
        "base_url_key": "dashscope",  # 指向 BASE_URL_CONFIG 中的某个 key
        "model": "qwen-max",  # 模型名称
        # 模型调用参数（每个模型可以独立配置）
        "max_tokens": 1024,  # 最大token数
        "temperature": 0.01, #裁判模型必须低温度
        # "top_p": 0.9,  # nucleus sampling参数
        # "frequency_penalty": 0.0,  # 频率惩罚
        # "presence_penalty": 0.0,  # 存在惩罚
        "timeout": 600,  # 超时时间（秒）
        # 流式输出配置
        # "stream": False,  # 是否使用流式输出（False=非流式，True=流式）
        # 思考模式配置（适用于 Qwen3、Qwen3-Omni-Flash、Qwen3-VL 模型）
        "enable_thinking": False,  # 是否开启思考模式（评判模型通常不需要）
        # extra_body 配置（非 OpenAI 标准参数，通过此字段传递）
        "extra_body": {}  # 额外的API参数（可选，如 {"enable_thinking": True}）
    },
    # 可以继续添加更多模型定义
    # "model5": {
    #     "base_url_key": "volces",
    #     "model": "qwen3-vl-plus",
    #     "max_tokens": 8192,
    #     "timeout": 600,
    #     "enable_thinking": True,
    #     "extra_body": {}
    # },
    # "model6": {
    #     "base_url_key": "siliconflow",
    #     "model": "z-ai/glm-4.6v",
    #     "max_tokens": 8192,
    #     "timeout": 600,
    #     "enable_thinking": True,
    #     "extra_body": {}
    # },
}

# ==================== 动态生成 API_CONFIG ====================
# 规则（与 evaluate/config.py 保持一致）：
# 1. 能被 OpenAI 兼容接口直接识别的超参数（model / max_tokens / temperature / top_p /
#    frequency_penalty / presence_penalty / stream / timeout 等），直接放到顶层。
# 2. 其它「不能直接读取」的参数（如 enable_thinking 之类的思考参数），自动合并进 extra_body，
#    同时在 API_CONFIG 顶层也保留一份，方便框架内部判断。
# 3. 如果用户在 MODEL_DEFINITIONS 里显式写了 extra_body，则自动在此基础上合并。

API_CONFIG = {}

# 顶层直传给 chat.completions.create 的标准字段
_TOP_LEVEL_KEYS = {
    "model",
    "max_tokens",
    "temperature",
    "top_p",
    "frequency_penalty",
    "presence_penalty",
    "stream",
    "timeout",
}

for model_key, model_def in MODEL_DEFINITIONS.items():
    base_url_key = model_def.get("base_url_key")
    if base_url_key not in BASE_URL_CONFIG:
        raise ValueError(
            f"模型 '{model_key}' 的 base_url_key '{base_url_key}' 在 BASE_URL_CONFIG 中不存在。"
            f"可用的配置: {list(BASE_URL_CONFIG.keys())}"
        )
    
    base_url_config = BASE_URL_CONFIG[base_url_key]
    
    # 基础必需字段
    api_conf = {
        "base_url": base_url_config["base_url"],
        "api_key": base_url_config["api_key"],
        "model": model_def["model"],
    }
    
    # 已有的 extra_body（用户显式配置）
    merged_extra_body = model_def.get("extra_body", {}).copy()
    
    # 遍历模型定义中的所有字段，自动拆分：
    # - 标准顶层参数：直接挂到 api_conf
    # - 其它参数：既保留在 api_conf 方便内部使用，也自动塞进 extra_body，保证请求体能拿到
    for k, v in model_def.items():
        if k in ("base_url_key", "extra_body", "model"):
            continue
        
        if k in _TOP_LEVEL_KEYS:
            api_conf[k] = v
        else:
            # 非标准字段（如 enable_thinking、未来扩展的 vendor 参数等）
            api_conf[k] = v
            # 放进 extra_body，保证请求体能拿到
            if k not in merged_extra_body:
                merged_extra_body[k] = v
    
    # 如果模型里根本没配 timeout，就给个默认的
    if "timeout" not in api_conf:
        api_conf["timeout"] = 600
    # 如果没配 max_tokens，也给个默认
    if "max_tokens" not in api_conf:
        api_conf["max_tokens"] = 8192
    
    api_conf["extra_body"] = merged_extra_body
    
    API_CONFIG[model_key] = api_conf


