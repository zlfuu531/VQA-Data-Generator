"""
测试错误处理功能的简单脚本
可以创建一些模拟数据来测试错误检测和重试逻辑
"""
import os
import sys
import json

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from module2.model_evaluation import Module2ModelEvaluation

def test_check_model_errors():
    """测试错误检测功能"""
    print("=" * 60)
    print("测试1: 错误检测功能")
    print("=" * 60)
    
    evaluator = Module2ModelEvaluation(debug_mode=True)
    
    # 测试用例1：正常情况（无错误）
    item1 = {
        "id": "test_001",
        "question": "测试问题",
        "answer": "测试答案",
        "model1": {
            "enabled": True,
            "answer": "模型1的答案",
            "process": "模型1的推理过程"
        },
        "model2": {
            "enabled": True,
            "answer": "模型2的答案",
            "process": "模型2的推理过程"
        },
        "model3": {
            "enabled": True,
            "answer": "模型3的答案",
            "process": "模型3的推理过程"
        }
    }
    
    error_info = evaluator._check_model_errors(item1)
    print("\n测试用例1：所有模型都正常")
    print(f"  has_error: {error_info['has_error']}")
    print(f"  error_models: {error_info['error_models']}")
    assert error_info['has_error'] == False, "应该没有错误"
    print("  ✅ 通过")
    
    # 测试用例2：model1 出错（单轮题答案为空）
    item2 = {
        "id": "test_002",
        "question": "测试问题",
        "answer": "测试答案",
        "model1": {
            "enabled": True,
            "answer": "",  # 空答案
            "process": "模型1的推理过程"
        },
        "model2": {
            "enabled": True,
            "answer": "模型2的答案",
            "process": "模型2的推理过程"
        },
        "model3": {
            "enabled": True,
            "answer": "模型3的答案",
            "process": "模型3的推理过程"
        }
    }
    
    error_info = evaluator._check_model_errors(item2)
    print("\n测试用例2：model1 出错（答案为空）")
    print(f"  has_error: {error_info['has_error']}")
    print(f"  error_models: {error_info['error_models']}")
    print(f"  error_details: {error_info['error_details']}")
    assert error_info['has_error'] == True, "应该有错误"
    assert "model1" in error_info['error_models'], "model1 应该在错误列表中"
    print("  ✅ 通过")
    
    # 测试用例3：多个模型出错
    item3 = {
        "id": "test_003",
        "question": "测试问题",
        "answer": "测试答案",
        "model1": {
            "enabled": True,
            "answer": "",  # 空答案
            "process": ""
        },
        "model2": {
            "enabled": True,
            "answer": "模型2的答案",
            "process": "模型2的推理过程"
        },
        "model3": {
            "enabled": True,
            "answer": "  ",  # 只有空格
            "process": ""
        }
    }
    
    error_info = evaluator._check_model_errors(item3)
    print("\n测试用例3：model1 和 model3 出错")
    print(f"  has_error: {error_info['has_error']}")
    print(f"  error_models: {error_info['error_models']}")
    print(f"  error_details: {error_info['error_details']}")
    assert error_info['has_error'] == True, "应该有错误"
    assert "model1" in error_info['error_models'], "model1 应该在错误列表中"
    assert "model3" in error_info['error_models'], "model3 应该在错误列表中"
    print("  ✅ 通过")
    
    # 测试用例4：多轮题出错
    item4 = {
        "id": "test_004",
        "question": {"round1": "问题1", "round2": "问题2"},  # 多轮题
        "answer": {"round1": "答案1", "round2": "答案2"},
        "model1": {
            "enabled": True,
            "answer": {"round1": "答案1", "round2": "答案2"},  # 正常
            "process": {"round1": "推理1", "round2": "推理2"}
        },
        "model2": {
            "enabled": True,
            "answer": {},  # 空字典
            "process": {}
        },
        "model3": {
            "enabled": True,
            "answer": {"round1": "答案1"},  # 缺少 round2
            "process": {"round1": "推理1"}
        }
    }
    
    error_info = evaluator._check_model_errors(item4)
    print("\n测试用例4：多轮题，model2 出错（答案为空字典）")
    print(f"  has_error: {error_info['has_error']}")
    print(f"  error_models: {error_info['error_models']}")
    print(f"  error_details: {error_info['error_details']}")
    assert error_info['has_error'] == True, "应该有错误"
    assert "model2" in error_info['error_models'], "model2 应该在错误列表中"
    # 注意：model3 虽然缺少 round2，但答案不为空，所以不算错误（这是业务逻辑的选择）
    print("  ✅ 通过")
    
    # 测试用例5：禁用的模型不检查
    item5 = {
        "id": "test_005",
        "question": "测试问题",
        "answer": "测试答案",
        "model1": {
            "enabled": False,  # 禁用
            "answer": "",  # 即使为空也不算错误
            "process": ""
        },
        "model2": {
            "enabled": True,
            "answer": "模型2的答案",
            "process": "模型2的推理过程"
        },
        "model3": {
            "enabled": True,
            "answer": "模型3的答案",
            "process": "模型3的推理过程"
        }
    }
    
    error_info = evaluator._check_model_errors(item5)
    print("\n测试用例5：model1 禁用（答案为空但不算错误）")
    print(f"  has_error: {error_info['has_error']}")
    print(f"  error_models: {error_info['error_models']}")
    assert error_info['has_error'] == False, "不应该有错误（model1 被禁用）"
    print("  ✅ 通过")
    
    print("\n" + "=" * 60)
    print("✅ 所有测试通过！")
    print("=" * 60)


def test_save_error_separation():
    """测试保存时错误分离功能"""
    print("\n" + "=" * 60)
    print("测试2: 保存时错误分离")
    print("=" * 60)
    
    # 创建临时测试目录
    import tempfile
    import shutil
    
    test_dir = tempfile.mkdtemp(prefix="module2_test_")
    print(f"\n临时测试目录: {test_dir}")
    
    try:
        evaluator = Module2ModelEvaluation(output_dir=test_dir, debug_mode=True)
        
        # 模拟结果：包含正常和错误的题目
        results = [
            # L1: 三个模型都对
            {
                "id": "q001",
                "question": "问题1",
                "answer": "答案1",
                "question_type": "单选题",
                "image_type": "图表",
                "model1": {"enabled": True, "answer": "A", "match_gt": True},
                "model2": {"enabled": True, "answer": "A", "match_gt": True},
                "model3": {"enabled": True, "answer": "A", "match_gt": True},
                "classification": {"level": "L1", "category": "三个模型都和GT相同", "agreement_count": 3}
            },
            # L2: 两个模型对
            {
                "id": "q002",
                "question": "问题2",
                "answer": "答案2",
                "question_type": "单选题",
                "image_type": "图表",
                "model1": {"enabled": True, "answer": "B", "match_gt": True},
                "model2": {"enabled": True, "answer": "B", "match_gt": True},
                "model3": {"enabled": True, "answer": "C", "match_gt": False},
                "classification": {"level": "L2", "category": "两个模型和GT相同", "agreement_count": 2}
            },
            # 错误1: model1 出错
            {
                "id": "q003",
                "question": "问题3",
                "answer": "答案3",
                "question_type": "单选题",
                "image_type": "图表",
                "model1": {"enabled": True, "answer": "", "match_gt": False},
                "model2": {"enabled": True, "answer": "D", "match_gt": False},
                "model3": {"enabled": True, "answer": "D", "match_gt": False},
                "model_error": {
                    "has_error": True,
                    "error_models": ["model1"],
                    "error_details": {"model1": "单轮题答案为空"}
                }
            },
            # L3: 一个模型对
            {
                "id": "q004",
                "question": "问题4",
                "answer": "答案4",
                "question_type": "多选题",
                "image_type": "照片",
                "model1": {"enabled": True, "answer": "AB", "match_gt": True},
                "model2": {"enabled": True, "answer": "AC", "match_gt": False},
                "model3": {"enabled": True, "answer": "BC", "match_gt": False},
                "classification": {"level": "L3", "category": "一个模型和GT相同", "agreement_count": 1}
            },
            # 错误2: model2 和 model3 出错
            {
                "id": "q005",
                "question": "问题5",
                "answer": "答案5",
                "question_type": "判断题",
                "image_type": "图表",
                "model1": {"enabled": True, "answer": "正确", "match_gt": False},
                "model2": {"enabled": True, "answer": "", "match_gt": False},
                "model3": {"enabled": True, "answer": "  ", "match_gt": False},
                "model_error": {
                    "has_error": True,
                    "error_models": ["model2", "model3"],
                    "error_details": {
                        "model2": "单轮题答案为空",
                        "model3": "单轮题答案为空"
                    }
                }
            }
        ]
        
        # 保存结果
        output_file = os.path.join(test_dir, "test_result.json")
        evaluator._save_by_level_and_summary(results, output_file)
        
        # 检查输出
        output_dir = os.path.join(test_dir, "test_result")
        
        # 检查 L1.json
        l1_path = os.path.join(output_dir, "L1.json")
        assert os.path.exists(l1_path), "L1.json 应该存在"
        with open(l1_path) as f:
            l1_data = json.load(f)
        print(f"\nL1.json: {len(l1_data)} 条")
        assert len(l1_data) == 1, "L1 应该有 1 条"
        assert l1_data[0]["id"] == "q001", "L1 应该是 q001"
        print("  ✅ L1.json 正确")
        
        # 检查 L2.json
        l2_path = os.path.join(output_dir, "L2.json")
        assert os.path.exists(l2_path), "L2.json 应该存在"
        with open(l2_path) as f:
            l2_data = json.load(f)
        print(f"L2.json: {len(l2_data)} 条")
        assert len(l2_data) == 1, "L2 应该有 1 条"
        print("  ✅ L2.json 正确")
        
        # 检查 L3.json
        l3_path = os.path.join(output_dir, "L3.json")
        assert os.path.exists(l3_path), "L3.json 应该存在"
        with open(l3_path) as f:
            l3_data = json.load(f)
        print(f"L3.json: {len(l3_data)} 条")
        assert len(l3_data) == 1, "L3 应该有 1 条"
        print("  ✅ L3.json 正确")
        
        # 检查 error.json
        error_path = os.path.join(output_dir, "error.json")
        assert os.path.exists(error_path), "error.json 应该存在"
        with open(error_path) as f:
            error_data = json.load(f)
        print(f"error.json: {len(error_data)} 条")
        assert len(error_data) == 2, "error.json 应该有 2 条"
        assert error_data[0]["id"] == "q003", "第一个错误应该是 q003"
        assert error_data[1]["id"] == "q005", "第二个错误应该是 q005"
        print("  ✅ error.json 正确")
        
        # 检查 summary.json
        summary_path = os.path.join(output_dir, "summary.json")
        assert os.path.exists(summary_path), "summary.json 应该存在"
        with open(summary_path) as f:
            summary = json.load(f)
        print(f"\nsummary.json:")
        print(f"  total_items: {summary['total_items']}")
        print(f"  error_items: {summary['error_items']}")
        assert summary["total_items"] == 3, "正常题目应该有 3 条"
        assert summary["error_items"] == 2, "错误题目应该有 2 条"
        print("  ✅ summary.json 正确")
        
        print("\n" + "=" * 60)
        print("✅ 保存功能测试通过！")
        print("=" * 60)
        
    finally:
        # 清理测试目录
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)
            print(f"\n已清理测试目录: {test_dir}")


if __name__ == "__main__":
    try:
        # 运行测试
        test_check_model_errors()
        test_save_error_separation()
        
        print("\n" + "=" * 60)
        print("🎉 所有测试通过！错误处理功能正常工作。")
        print("=" * 60)
        
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

