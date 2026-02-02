#!/usr/bin/env python3
"""
配置验证脚本
运行前检查所有必需配置，验证 API Key 格式，检查文件路径有效性
"""
import os
import sys
import re
from pathlib import Path
from typing import List, Tuple, Dict, Any

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 颜色输出支持
class Colors:
    """ANSI 颜色代码"""
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_error(message: str, suggestion: str = ""):
    """统一错误提示格式"""
    print(f"{Colors.RED}❌ 错误：{message}{Colors.RESET}")
    if suggestion:
        print(f"   {Colors.YELLOW}💡 建议：{suggestion}{Colors.RESET}")

def print_warning(message: str, suggestion: str = ""):
    """统一警告提示格式"""
    print(f"{Colors.YELLOW}⚠️  警告：{message}{Colors.RESET}")
    if suggestion:
        print(f"   {Colors.YELLOW}💡 建议：{suggestion}{Colors.RESET}")

def print_success(message: str):
    """统一成功提示格式"""
    print(f"{Colors.GREEN}✅ {message}{Colors.RESET}")

def print_info(message: str):
    """统一信息提示格式"""
    print(f"{Colors.CYAN}ℹ️  {message}{Colors.RESET}")

def print_section(title: str):
    """打印章节标题"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{title}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}\n")


def validate_api_key_format(api_key: str, key_name: str) -> Tuple[bool, str]:
    """
    验证 API Key 格式
    
    Args:
        api_key: API Key 值
        key_name: API Key 名称（用于错误提示）
    
    Returns:
        (是否有效, 错误信息)
    """
    if not api_key or api_key.strip() == "":
        return False, f"{key_name} 为空"
    
    if api_key in ["your-api-key-here", "your_dashscope_api_key", 
                   "your_volces_api_key", "your_openrouter_api_key", 
                   "your_siliconflow_api_key"]:
        return False, f"{key_name} 仍为默认占位符"
    
    # 基本格式检查：至少10个字符
    if len(api_key) < 10:
        return False, f"{key_name} 长度过短（至少10个字符）"
    
    # 检查是否包含空格
    if ' ' in api_key:
        return False, f"{key_name} 包含空格（可能配置错误）"
    
    return True, ""


def check_file_path(file_path: str, path_type: str = "文件") -> Tuple[bool, str]:
    """
    检查文件路径有效性
    
    Args:
        file_path: 文件路径
        path_type: 路径类型（用于错误提示）
    
    Returns:
        (是否有效, 错误信息)
    """
    if not file_path or file_path.strip() == "":
        return False, f"{path_type}路径为空"
    
    # 检查占位符
    placeholders = ["绝对路径", "绝对路径/题目.jsonl", "绝对路径题目.jsonl"]
    if any(ph in file_path for ph in placeholders):
        return False, f"{path_type}路径仍为占位符"
    
    path = Path(file_path)
    
    # 检查是否为绝对路径或相对路径
    if not path.is_absolute() and not path.exists():
        # 相对路径：检查相对于项目根目录
        abs_path = project_root / path
        if not abs_path.exists():
            return False, f"{path_type}不存在: {file_path}"
    
    if path.is_absolute() and not path.exists():
        return False, f"{path_type}不存在: {file_path}"
    
    # 检查是否为文件（如果是文件路径）
    if path_type == "文件" and path.exists() and not path.is_file():
        return False, f"路径不是文件: {file_path}"
    
    # 检查是否为目录（如果是目录路径）
    if path_type == "目录" and path.exists() and not path.is_dir():
        return False, f"路径不是目录: {file_path}"
    
    # 检查读取权限
    if path.exists() and path.is_file() and not os.access(path, os.R_OK):
        return False, f"文件无读取权限: {file_path}"
    
    return True, ""


def check_directory_path(dir_path: str, create_if_not_exists: bool = False) -> Tuple[bool, str]:
    """
    检查目录路径有效性
    
    Args:
        dir_path: 目录路径
        create_if_not_exists: 如果不存在是否创建
    
    Returns:
        (是否有效, 错误信息)
    """
    if not dir_path or dir_path.strip() == "":
        return False, "目录路径为空"
    
    path = Path(dir_path)
    
    # 如果是相对路径，转换为绝对路径
    if not path.is_absolute():
        path = project_root / path
    
    # 如果目录不存在
    if not path.exists():
        if create_if_not_exists:
            try:
                path.mkdir(parents=True, exist_ok=True)
                return True, ""
            except Exception as e:
                return False, f"无法创建目录: {e}"
        else:
            return False, f"目录不存在: {dir_path}"
    
    # 检查是否为目录
    if not path.is_dir():
        return False, f"路径不是目录: {dir_path}"
    
    # 检查写入权限
    if not os.access(path, os.W_OK):
        return False, f"目录无写入权限: {dir_path}"
    
    return True, ""


def check_module1_config() -> List[Tuple[str, bool, str]]:
    """检查 Module1 配置"""
    results = []
    
    script_path = project_root / "module1" / "github_template.sh"
    if not script_path.exists():
        results.append(("Module1脚本", False, f"找不到脚本文件: {script_path}"))
        return results
    
    # 读取脚本内容
    try:
        with open(script_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 检查 INPUT_FILE
        input_match = re.search(r'INPUT_FILE="([^"]+)"', content)
        if input_match:
            input_file = input_match.group(1)
            if input_file and not any(ph in input_file for ph in ["绝对路径", "/path/to"]):
                valid, error = check_file_path(input_file, "输入文件")
                results.append(("Module1输入文件", valid, error if not valid else "✓"))
            else:
                results.append(("Module1输入文件", False, "INPUT_FILE 仍为占位符"))
        else:
            results.append(("Module1输入文件", False, "未找到 INPUT_FILE 配置"))
        
        # 检查 API_KEY
        api_key_match = re.search(r'API_KEY="([^"]+)"', content)
        if api_key_match:
            api_key = api_key_match.group(1)
            valid, error = validate_api_key_format(api_key, "API_KEY")
            results.append(("Module1 API Key", valid, error if not valid else "✓"))
        else:
            results.append(("Module1 API Key", False, "未找到 API_KEY 配置"))
        
        # 检查 OUTPUT_FILE
        output_match = re.search(r'OUTPUT_FILE="([^"]+)"', content)
        if output_match:
            output_file = output_match.group(1)
            # 提取目录部分
            output_dir = str(Path(output_file).parent)
            valid, error = check_directory_path(output_dir, create_if_not_exists=True)
            results.append(("Module1输出目录", valid, error if not valid else "✓"))
        
    except Exception as e:
        results.append(("Module1配置读取", False, f"读取配置失败: {e}"))
    
    return results


def check_module2_config() -> List[Tuple[str, bool, str]]:
    """检查 Module2 配置"""
    results = []
    
    # 检查 .env 文件
    env_file = project_root / ".env"
    env_exists = env_file.exists()
    results.append((".env文件", env_exists, "文件不存在" if not env_exists else "✓"))
    
    if env_exists:
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file)
        except ImportError:
            pass
        
        # 检查 API Keys
        api_keys = {
            "api1": os.getenv("api1", ""),
            "api2": os.getenv("api2", ""),
            "api3": os.getenv("api3", ""),
            "api4": os.getenv("api4", ""),
        }
        
        for key_name, key_value in api_keys.items():
            valid, error = validate_api_key_format(key_value, key_name)
            results.append((f"Module2 {key_name}", valid, error if not valid else "✓"))
    
    # 检查 config.py
    config_path = project_root / "module2" / "config.py"
    if config_path.exists():
        try:
            sys.path.insert(0, str(project_root / "module2"))
            from module2.config import MODEL_CONFIG, API_CONFIG
            results.append(("Module2 config.py", True, "✓"))
            
            # 检查模型配置
            enabled_models = [k for k, v in MODEL_CONFIG.items() 
                            if isinstance(v, dict) and v.get("enabled", False)]
            if enabled_models:
                results.append(("Module2启用模型", True, f"已启用: {', '.join(enabled_models)}"))
            else:
                results.append(("Module2启用模型", False, "未启用任何模型"))
        except Exception as e:
            results.append(("Module2 config.py", False, f"加载失败: {e}"))
    
    # 检查 main.sh
    script_path = project_root / "module2" / "main.sh"
    if script_path.exists():
        try:
            with open(script_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            input_match = re.search(r'INPUT_FILE="([^"]+)"', content)
            if input_match:
                input_file = input_match.group(1)
                if any(ph in input_file for ph in ["绝对路径", "/path/to"]):
                    results.append(("Module2输入文件", False, "INPUT_FILE 仍为占位符"))
                else:
                    valid, error = check_file_path(input_file, "输入文件")
                    results.append(("Module2输入文件", valid, error if not valid else "✓"))
        except Exception as e:
            results.append(("Module2脚本读取", False, f"读取失败: {e}"))
    
    return results


def check_evaluate_config() -> List[Tuple[str, bool, str]]:
    """检查 Evaluate 配置"""
    results = []
    
    # 检查 .env 文件（与 Module2 共享）
    env_file = project_root / ".env"
    env_exists = env_file.exists()
    
    if env_exists:
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file)
        except ImportError:
            pass
        
        # 检查 EVAL_MODELS
        eval_models = os.getenv("EVAL_MODELS", "")

        # 如果环境变量里没有，再尝试从 run_eval.sh 中读取
        script_models_source = None
        if not eval_models:
            script_path = project_root / "evaluate" / "run_eval.sh"
            if script_path.exists():
                try:
                    with open(script_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    # 兼容：EVAL_MODELS="a,b,c" 或 EVAL_MODELS='a,b,c'
                    m = re.search(r'EVAL_MODELS\s*=\s*["\']([^"\']*)["\']', content)
                    if m:
                        eval_models = m.group(1)
                        script_models_source = "run_eval.sh"
                except Exception as e:
                    results.append(("Evaluate模型列表", False, f"从 run_eval.sh 解析失败: {e}"))

        if eval_models:
            models = [m.strip() for m in eval_models.split(",") if m.strip()]
            if models:
                # 验证模型是否在配置中
                try:
                    sys.path.insert(0, str(project_root / "evaluate"))
                    from evaluate.config import MODEL_DEFINITIONS
                    invalid_models = [m for m in models if m not in MODEL_DEFINITIONS]
                    if invalid_models:
                        results.append((
                            "Evaluate模型列表",
                            False,
                            f"无效模型: {', '.join(invalid_models)}（请检查 evaluate/config.py 的 MODEL_DEFINITIONS 或 run_eval.sh/.env 中的 EVAL_MODELS）",
                        ))
                    else:
                        source_note = "（来自环境变量 EVAL_MODELS）"
                        if script_models_source == "run_eval.sh":
                            source_note = "（未在 .env 设置，从 run_eval.sh 中解析）"
                        results.append((
                            "Evaluate模型列表",
                            True,
                            f"已配置: {', '.join(models)} {source_note}",
                        ))
                except Exception as e:
                    results.append(("Evaluate模型列表", False, f"验证失败: {e}"))
            else:
                results.append(("Evaluate模型列表", False, "EVAL_MODELS 为空"))
        else:
            results.append(("Evaluate模型列表", False, "未在 .env 或 run_eval.sh 中检测到 EVAL_MODELS"))
    
    # 检查 run_eval.sh
    script_path = project_root / "evaluate" / "run_eval.sh"
    if script_path.exists():
        try:
            with open(script_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            input_match = re.search(r'INPUT_FILE="([^"]+)"', content)
            if input_match:
                input_file = input_match.group(1)
                valid, error = check_file_path(input_file, "输入文件")
                results.append(("Evaluate输入文件", valid, error if not valid else "✓"))
        except Exception as e:
            results.append(("Evaluate脚本读取", False, f"读取失败: {e}"))
    
    # 检查输出目录
    output_dir = project_root / "evaluate" / "outputs"
    valid, error = check_directory_path(str(output_dir), create_if_not_exists=True)
    results.append(("Evaluate输出目录", valid, error if not valid else "✓"))
    
    return results


def main():
    """主函数"""
    print_section("配置验证脚本")
    print_info("正在检查所有模块的配置...")
    
    all_results = []
    all_passed = True
    
    # 检查 Module1
    print_section("Module1 - 问题生成")
    module1_results = check_module1_config()
    all_results.extend(module1_results)
    
    for name, passed, message in module1_results:
        if passed:
            print_success(f"{name}: {message}")
        else:
            print_error(f"{name}: {message}")
            all_passed = False
    
    # 检查 Module2
    print_section("Module2 - 难度分级")
    module2_results = check_module2_config()
    all_results.extend(module2_results)
    
    for name, passed, message in module2_results:
        if passed:
            print_success(f"{name}: {message}")
        else:
            print_error(f"{name}: {message}")
            all_passed = False
    
    # 检查 Evaluate
    print_section("Evaluate - 金融领域评测框架")
    evaluate_results = check_evaluate_config()
    all_results.extend(evaluate_results)
    
    for name, passed, message in evaluate_results:
        if passed:
            print_success(f"{name}: {message}")
        else:
            print_error(f"{name}: {message}")
            all_passed = False
    
    # 总结
    print_section("验证结果")
    total = len(all_results)
    passed_count = sum(1 for _, passed, _ in all_results if passed)
    failed_count = total - passed_count
    
    print_info(f"总计: {total} 项检查")
    print_success(f"通过: {passed_count} 项")
    if failed_count > 0:
        print_error(f"失败: {failed_count} 项")
    
    if all_passed:
        print_success("\n🎉 所有配置检查通过！可以开始运行。")
        return 0
    else:
        print_error("\n⚠️  存在配置问题，请先修复后再运行。")
        print_info("\n💡 提示：")
        print_info("  1. 检查 .env 文件中的 API Key 配置")
        print_info("  2. 检查各模块脚本中的文件路径配置")
        print_info("  3. 参考 .env.example 文件进行配置")
        return 1


if __name__ == "__main__":
    sys.exit(main())

