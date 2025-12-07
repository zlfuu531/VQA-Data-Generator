"""
配置文件：存储所有配置信息

⚠️ 注意：这里不再硬编码任何真实的 API Key，所有密钥都从环境变量读取。
推荐在本机使用 `.env` 或 shell 中 `export` 的方式设置环境变量。
"""
import os
from pickle import FALSE


def _get_env(key: str, default: str = "") -> str:
    """
    从环境变量读取配置，提供默认值。
    单独封装主要是为了后续如果需要做日志/校验会更集中。
    """
    return os.getenv(key, default)


# MODEL_CONFIG 中的 name 字段会指向这里的 key
API_CONFIG = {
    "model1": {  # 配置标识符，可以自定义为任何名称（如 "model1_api", "api_config_1" 等）
        #"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        #"base_url": "https://api.moonshot.cn/v1",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        # 从环境变量读取模型1的 API Key（例如：export QA_PIPELINE_MODEL1_API_KEY=xxx）
        "api_key": _get_env("QA_PIPELINE_MODEL2_API_KEY"),
        #"model": "qwen3-vl-plus",
        "model": "doubao-seed-1-6-251015",
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
    "model2": {  # 配置标识符，可以自定义为任何名称
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        # 从环境变量读取模型2的 API Key（例如：export QA_PIPELINE_MODEL2_API_KEY=xxx）
        "api_key": _get_env("QA_PIPELINE_MODEL2_API_KEY"),
        "model": "doubao-seed-1-6-vision-250815",
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
        # "enable_thinking": True,  # 是否开启思考模式（开启后，思考内容通过 reasoning_content 字段返回）
        # extra_body 配置（非 OpenAI 标准参数，通过此字段传递）
        "extra_body": {}  # 额外的API参数（可选，如 {"enable_thinking": True}）
    },
    "model3": {  # 配置标识符，可以自定义为任何名称
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        # 从环境变量读取模型3的 API Key（例如：export QA_PIPELINE_MODEL3_API_KEY=xxx）
        "api_key": _get_env("QA_PIPELINE_MODEL3_API_KEY"),
        "model": "qwen-vl-max",
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
    "model4": {  # 配置标识符，可以自定义为任何名称（如 "model1_api", "api_config_1" 等）
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        # 裁判模型的 API Key（例如：export QA_PIPELINE_JUDGE_API_KEY=xxx）
        "api_key": _get_env("QA_PIPELINE_JUDGE_API_KEY"),
        "model": "qwen-max",
        # 模型调用参数（每个模型可以独立配置）
        "temperature": 0.01,  # 温度参数，控制随机性（评判模型使用低温度）
        "max_tokens": 512,  # 最大token数
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
    }
}

# 模型配置 - 可以开关每个模型
# name 字段必须指向 API_CONFIG 中的某个 key
# 例如：如果 API_CONFIG 中有 "my_custom_api" 这个 key，那么 name 可以设置为 "my_custom_api"
MODEL_CONFIG = {
    "model1": {
        "name": "model1",  # 指向 API_CONFIG 中的某个 key（可以自定义）
        "enabled": True    # 是否启用
    },
    "model2": {
        "name": "model2",  # 指向 API_CONFIG 中的某个 key（可以自定义）
        "enabled": True
    },
    "model3": {
        "name": "model3",  # 指向 API_CONFIG 中的某个 key（可以自定义）
        "enabled": True
    },
    "judge_model": "model4"  # 裁判模型使用的API配置（指向API_CONFIG中的key，可以自定义）
}
