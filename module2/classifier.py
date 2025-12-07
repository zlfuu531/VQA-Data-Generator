"""
分类模块
根据模型与GT的一致性对QA对进行分类（L1, L2, L3, L4）
基于每个模型的 match_gt 字段（来自 judge 的结果）进行分类
- L1: 三个模型都和GT相同
- L2: 两个模型和GT相同
- L3: 一个模型和GT相同
- L4: 所有模型都和GT不同
"""
import os
import sys
from typing import List, Dict

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 不再需要导入工具函数，分类逻辑已简化


class QAClassifier:
    """QA分类器"""
    
    def __init__(self):
        pass
    
    def classify_qa_item(self, qa_item: Dict) -> Dict:
        """
        对单个QA项进行分类
        
        分类规则（基于每个模型的 match_gt 字段）：
        - L1: 三个模型都和GT相同（match_gt=True）
        - L2: 两个模型和GT相同
        - L3: 一个模型和GT相同
        - L4: 所有模型都和GT不同（agreement_count=0）
        """
        # 安全获取字段，提供默认值
        model1 = qa_item.get("model1", {})
        model2 = qa_item.get("model2", {})
        model3 = qa_item.get("model3", {})
        
        # 确保是字典类型
        if not isinstance(model1, dict):
            model1 = {}
        if not isinstance(model2, dict):
            model2 = {}
        if not isinstance(model3, dict):
            model3 = {}
        
        # 获取每个模型的启用状态和 match_gt 字段（来自 judge 的结果）
        model1_enabled = model1.get("enabled", False)
        model2_enabled = model2.get("enabled", False)
        model3_enabled = model3.get("enabled", False)
        
        model1_match_gt = model1.get("match_gt", False) if model1_enabled else False
        model2_match_gt = model2.get("match_gt", False) if model2_enabled else False
        model3_match_gt = model3.get("match_gt", False) if model3_enabled else False
        
        # 统计与GT一致的模型数量（基于 match_gt 字段）
        match_gt_list = []
        if model1_enabled:
            match_gt_list.append(model1_match_gt)
        if model2_enabled:
            match_gt_list.append(model2_match_gt)
        if model3_enabled:
            match_gt_list.append(model3_match_gt)
        
        agreement_count = sum(match_gt_list)  # 统计 match_gt=True 的数量
        
        # 如果没有启用的模型，默认为 L4
        enabled_count = len(match_gt_list)
        if enabled_count == 0:
            classification = {
                "level": "L4",
                "category": "无启用的模型",
                "agreement_count": 0
            }
            qa_item["classification"] = classification
            return qa_item
        
        # 根据分类规则进行分类
        if agreement_count == 3:
            # L1: 三个模型都和GT相同
            level = "L1"
            category = "三个模型都和GT相同"
        elif agreement_count == 2:
            # L2: 两个模型和GT相同
            level = "L2"
            category = "两个模型和GT相同"
        elif agreement_count == 1:
            # L3: 一个模型和GT相同
            level = "L3"
            category = "一个模型和GT相同"
        elif agreement_count == 0:
            # L4: 所有模型都和GT不同
            level = "L4"
            category = "所有模型都和GT不同"
        else:
            # 异常情况（不应该发生）
            level = "L4"
            category = f"异常情况：agreement_count={agreement_count}"
        
        # 构建分类结果
        classification = {
            "level": level,
            "category": category,
            "agreement_count": agreement_count
        }
        
        qa_item["classification"] = classification
        return qa_item

