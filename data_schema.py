"""
数据格式定义和示例
统一所有JSON文件的字段格式
"""
import json
import os
from typing import Dict, Any
from datetime import datetime
from utils import save_json, ensure_dir

# 输入文件格式（模块1输入）
INPUT_SCHEMA = {
    "id": "唯一标识符",
    "type": "图片类型（如：chart, diagram, text等）",
    "image_path": "图片路径"
}

# 模块1输出格式（QA生成后）
MODULE1_OUTPUT_SCHEMA = {
    "id": "唯一标识符",
    "type": "图片类型",
    "image_path": "图片路径",
    "question": "生成的问题",
    "process": "问题生成过程/思考过程",
    "options": {
        "A": "选项A（如果是选择题）",
        "B": "选项B（如果是选择题）",
        "C": "选项C（如果是选择题）",
        "D": "选项D（如果是选择题）"
    },
    "answer": "标准答案（GT）"
}

# 模块2输出格式（模型检验后）
MODULE2_OUTPUT_SCHEMA = {
    # 继承模块1的所有字段
    "id": "唯一标识符",
    "type": "图片类型",
    "image_path": "图片路径",
    "question": "问题",
    "process": "问题生成过程",
    "options": "选项（如果是选择题）",
    "answer": "标准答案（GT）",
    
    # 模型1输出
    "model1": {
        "enabled": "是否启用",
        "process": "模型1的思考过程",
        "answer": "模型1的答案",
        "model_name": "模型名称",
        "response_time": "响应时间",
        "match_gt": "是否与GT相同（True/False）"
    },
    # 模型2输出
    "model2": {
        "enabled": "是否启用",
        "process": "模型2的思考过程",
        "answer": "模型2的答案",
        "model_name": "模型名称",
        "response_time": "响应时间",
        "match_gt": "是否与GT相同（True/False）"
    },
    # 模型3输出
    "model3": {
        "enabled": "是否启用",
        "process": "模型3的思考过程",
        "answer": "模型3的答案",
        "model_name": "模型名称",
        "response_time": "响应时间",
        "match_gt": "是否与GT相同（True/False）"
    },
    # 问题分类
    "classification": {
        "level": "分类级别（L0/L1/L2/L3/L4）",
        "category": "分类类别",
        "agreement_count": "与GT一致的模型数量（基于match_gt字段）",
        "all_models_same": "所有模型答案是否一致",
        "two_models_same": "是否有两个模型答案一致",
        "all_models_different": "所有模型答案是否不同"
    }
}


def create_example_input() -> Dict[str, Any]:
    """创建输入文件示例"""
    return {
        "items": [
            {
                "id": "item_001",
                "type": "chart",
                "image_path": "/path/to/image1.jpg"
            },
            {
                "id": "item_002",
                "type": "diagram",
                "image_path": "/path/to/image2.jpg"
            }
        ],
        "metadata": {
            "source": "input_file",
            "created_at": datetime.now().isoformat(),
            "total_items": 2
        }
    }


def create_example_module1_output() -> Dict[str, Any]:
    """创建模块1输出示例"""
    return {
        "items": [
            {
                "id": "item_001",
                "type": "chart",
                "image_path": "/path/to/image1.jpg",
                "question": "这张图表展示了什么数据？",
                "process": "分析图表类型、数据内容、趋势等",
                "options": {
                    "A": "",
                    "B": "",
                    "C": "",
                    "D": ""
                },
                "answer": "这张图表展示了2023年的销售数据，显示了逐月增长的趋势。"
            },
            {
                "id": "item_002",
                "type": "diagram",
                "image_path": "/path/to/image2.jpg",
                "question": "根据图表，选择正确的答案：",
                "process": "识别图表类型，提取关键信息",
                "options": {
                    "A": "选项A内容",
                    "B": "选项B内容",
                    "C": "选项C内容",
                    "D": "选项D内容"
                },
                "answer": "B"
            }
        ],
        "metadata": {
            "source": "module1_output",
            "created_at": datetime.now().isoformat(),
            "total_items": 2
        }
    }


def create_example_module2_output() -> Dict[str, Any]:
    """创建模块2输出示例"""
    return {
        "items": [
            {
                "id": "item_001",
                "type": "chart",
                "image_path": "/path/to/image1.jpg",
                "question": "这张图表展示了什么数据？",
                "process": "分析图表类型、数据内容、趋势等",
                "options": {
                    "A": "",
                    "B": "",
                    "C": "",
                    "D": ""
                },
                "answer": "这张图表展示了2023年的销售数据，显示了逐月增长的趋势。",
                "model1": {
                    "enabled": True,
                    "process": "首先观察图表类型...",
                    "answer": "这张图表展示了2023年的销售数据，显示了逐月增长的趋势。",
                    "model_name": "doubao",
                    "response_time": 2.5,
                    "match_gt": True
                },
                "model2": {
                    "enabled": True,
                    "process": "分析图表内容...",
                    "answer": "图表显示销售数据增长",
                    "model_name": "qwen",
                    "response_time": 2.3,
                    "match_gt": False
                },
                "model3": {
                    "enabled": True,
                    "process": "识别图表特征...",
                    "answer": "这张图表展示了2023年的销售数据，显示了逐月增长的趋势。",
                    "model_name": "ds",
                    "response_time": 2.7,
                    "match_gt": True
                },
                "classification": {
                    "level": "L2",
                    "category": "QA正确，进阶样本",
                    "agreement_count": 2,
                    "all_models_same": False,
                    "two_models_same": True,
                    "all_models_different": False
                }
            }
        ],
        "metadata": {
            "source": "module2_output",
            "created_at": datetime.now().isoformat(),
            "total_items": 1
        }
    }


def save_example_files(output_dir: str):
    """保存示例文件到输出目录"""
    ensure_dir(output_dir)
    
    # 保存输入示例
    example_input = create_example_input()
    save_json(example_input, os.path.join(output_dir, "example_input.json"))
    
    # 保存模块1输出示例
    example_module1 = create_example_module1_output()
    save_json(example_module1, os.path.join(output_dir, "example_module1_output.json"))
    
    # 保存模块2输出示例
    example_module2 = create_example_module2_output()
    save_json(example_module2, os.path.join(output_dir, "example_module2_output.json"))
    
    # 保存schema说明
    schemas = {
        "input_schema": INPUT_SCHEMA,
        "module1_output_schema": MODULE1_OUTPUT_SCHEMA,
        "module2_output_schema": MODULE2_OUTPUT_SCHEMA
    }
    save_json(schemas, os.path.join(output_dir, "schemas.json"))
    
    print(f"✅ 示例文件已保存到: {output_dir}")
