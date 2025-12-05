"""
模型调用模块
包含三个模型的API调用函数
每个模型都是独立文件，可以直接调用
"""
from models.model1 import call_model1_api
from models.model2 import call_model2_api
from models.model3 import call_model3_api

__all__ = [
    'call_model1_api', 'call_model2_api', 'call_model3_api'
]
