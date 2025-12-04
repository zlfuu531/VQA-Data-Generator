"""
测试模块2的完整流程
验证：三个模型调用 -> 答案比对 -> 分级
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from module2.model_evaluation import Module2ModelEvaluation
from utils import load_json, save_json


def create_test_input():
    """创建测试输入数据"""
    test_data = {
        "items": [
            {
                "id": "test_001",
                "type": "chart",
                "image_path": "/path/to/test_image.jpg",  # 实际使用时需要真实路径
                "question": "这张图表展示了什么数据？",
                "process": "分析图表类型、数据内容",
                "options": {
                    "A": "",
                    "B": "",
                    "C": "",
                    "D": ""
                },
                "answer": "这张图表展示了2023年的销售数据。"
            }
        ],
        "metadata": {
            "source": "test",
            "created_at": "2024-01-01T10:00:00"
        }
    }
    
    test_file = "./test_module1_output.json"
    save_json(test_data, test_file)
    print(f"✅ 创建测试输入文件: {test_file}")
    return test_file


def test_module2_flow():
    """测试模块2的完整流程"""
    print("=" * 60)
    print("测试模块2完整流程")
    print("=" * 60)
    
    # 创建测试输入
    test_input = create_test_input()
    
    # 创建评估器
    evaluator = Module2ModelEvaluation()
    
    # 测试单个item的完整流程
    print("\n测试单个item的完整流程：")
    test_item = {
        "id": "test_001",
        "type": "chart",
        "image_path": "/path/to/test_image.jpg",
        "question": "这张图表展示了什么数据？",
        "process": "分析图表类型",
        "options": {"A": "", "B": "", "C": "", "D": ""},
        "answer": "这张图表展示了2023年的销售数据。"
    }
    
    print("\n1. 测试步骤1：调用三个模型")
    try:
        result_step1 = evaluator.step1_call_models(test_item)
        print("   ✅ 步骤1完成")
        print(f"   - model1 enabled: {result_step1.get('model1', {}).get('enabled', False)}")
        print(f"   - model2 enabled: {result_step1.get('model2', {}).get('enabled', False)}")
        print(f"   - model3 enabled: {result_step1.get('model3', {}).get('enabled', False)}")
    except Exception as e:
        print(f"   ❌ 步骤1失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print("\n2. 测试步骤2：比对答案与GT")
    try:
        result_step2 = evaluator.step2_compare_with_gt(result_step1)
        print("   ✅ 步骤2完成")
        for model_key in ["model1", "model2", "model3"]:
            model_data = result_step2.get(model_key, {})
            if model_data.get("enabled", False):
                match_gt = model_data.get("match_gt", False)
                print(f"   - {model_key} match_gt: {match_gt}")
    except Exception as e:
        print(f"   ❌ 步骤2失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print("\n3. 测试步骤3：分级")
    try:
        result_step3 = evaluator.step3_classify(result_step2)
        print("   ✅ 步骤3完成")
        classification = result_step3.get("classification", {})
        print(f"   - level: {classification.get('level', 'N/A')}")
        print(f"   - category: {classification.get('category', 'N/A')}")
        print(f"   - agreement_count: {classification.get('agreement_count', 0)}")
    except Exception as e:
        print(f"   ❌ 步骤3失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print("\n4. 测试完整流程：evaluate_item")
    try:
        final_result = evaluator.evaluate_item(test_item)
        print("   ✅ 完整流程完成")
        print(f"   - 包含model1: {'model1' in final_result}")
        print(f"   - 包含model2: {'model2' in final_result}")
        print(f"   - 包含model3: {'model3' in final_result}")
        print(f"   - 包含classification: {'classification' in final_result}")
        print(f"   - 包含comparison: {'comparison' in final_result}")
        
        # 保存测试结果
        test_output = {
            "items": [final_result],
            "metadata": {
                "source": "test_module2",
                "test_passed": True
            }
        }
        save_json(test_output, "./test_module2_output.json")
        print(f"\n   ✅ 测试结果已保存到: ./test_module2_output.json")
        
    except Exception as e:
        print(f"   ❌ 完整流程失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print("\n" + "=" * 60)
    print("✅ 所有测试通过！")
    print("=" * 60)


if __name__ == "__main__":
    test_module2_flow()

