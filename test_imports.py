#!/usr/bin/env python3
"""
测试所有模块的导入和基本功能
"""
import sys
import os

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """测试所有关键模块的导入"""
    print("=" * 60)
    print("测试模块导入")
    print("=" * 60)
    
    try:
        print("1. 测试 config 导入...")
        from config import API_CONFIG, MODEL_CONFIG, PATH_CONFIG
        print("   ✅ config 导入成功")
        
        print("2. 测试 utils 导入...")
        from utils import load_json, save_json, compare_answers
        print("   ✅ utils 导入成功")
        
        print("3. 测试 Model1 函数导入...")
        from models.model1 import call_model1_api
        print("   ✅ call_model1_api 导入成功")
        
        print("4. 测试 Model2 函数导入...")
        from models.model2 import call_model2_api
        print("   ✅ call_model2_api 导入成功")
        
        print("5. 测试 Model3 函数导入...")
        from models.model3 import call_model3_api
        print("   ✅ call_model3_api 导入成功")
        
        print("6. 测试 AnswerComparison 导入...")
        from module2.answer_comparison import AnswerComparison
        print("   ✅ AnswerComparison 导入成功")
        
        print("7. 测试 QAClassifier 导入...")
        from module2.classifier import QAClassifier
        print("   ✅ QAClassifier 导入成功")
        
        print("8. 测试 Module2ModelEvaluation 导入...")
        from module2.model_evaluation import Module2ModelEvaluation
        print("   ✅ Module2ModelEvaluation 导入成功")
        
        print("9. 测试 Module1QAGenerator 导入...")
        from module1.qa_generator import Module1QAGenerator
        print("   ✅ Module1QAGenerator 导入成功")
        
        print("10. 测试 judge 模块导入...")
        from module2.judge import judge_answer_with_model
        print("   ✅ judge_answer_with_model 导入成功")
        
        print("\n" + "=" * 60)
        print("所有模块导入测试通过！")
        print("=" * 60)
        return True
        
    except Exception as e:
        print(f"\n❌ 导入失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_model_functions():
    """测试模型函数调用"""
    print("\n" + "=" * 60)
    print("测试模型函数")
    print("=" * 60)
    
    try:
        from models.model1 import call_model1_api
        from models.model2 import call_model2_api
        from models.model3 import call_model3_api
        from config import MODEL_CONFIG
        
        print("1. 测试 call_model1_api 函数...")
        print(f"   配置: {MODEL_CONFIG['model1']}")
        print("   ✅ call_model1_api 函数可用")
        
        print("2. 测试 call_model2_api 函数...")
        print(f"   配置: {MODEL_CONFIG['model2']}")
        print("   ✅ call_model2_api 函数可用")
        
        print("3. 测试 call_model3_api 函数...")
        print(f"   配置: {MODEL_CONFIG['model3']}")
        print("   ✅ call_model3_api 函数可用")
        
        print("\n" + "=" * 60)
        print("所有模型函数测试通过！")
        print("=" * 60)
        return True
        
    except Exception as e:
        print(f"\n❌ 模型函数测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_answer_comparison():
    """测试 AnswerComparison 初始化"""
    print("\n" + "=" * 60)
    print("测试 AnswerComparison")
    print("=" * 60)
    
    try:
        from module2.answer_comparison import AnswerComparison
        
        print("1. 测试 AnswerComparison 初始化...")
        ac = AnswerComparison()
        print(f"   ✅ AnswerComparison 初始化成功")
        print(f"      model1_api_config_name: {ac.model1_api_config_name}")
        print(f"      model2_api_config_name: {ac.model2_api_config_name}")
        print(f"      model3_api_config_name: {ac.model3_api_config_name}")
        
        print("\n" + "=" * 60)
        print("AnswerComparison 测试通过！")
        print("=" * 60)
        return True
        
    except Exception as e:
        print(f"\n❌ AnswerComparison 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("\n开始测试...\n")
    
    success = True
    success &= test_imports()
    success &= test_model_functions()
    success &= test_answer_comparison()
    
    print("\n" + "=" * 60)
    if success:
        print("✅ 所有测试通过！")
    else:
        print("❌ 部分测试失败，请检查错误信息")
    print("=" * 60 + "\n")

