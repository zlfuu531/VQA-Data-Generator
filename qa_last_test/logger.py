"""
多次回答筛题脚本的详细日志工具：
- 统一管理日志文件（logs 目录下）
- 提供初始化、记录问题处理、记录模型响应、关闭日志的函数
"""
import os
import time
import json
import threading
from typing import Optional, Dict, Any

# 外部模块（evaluate_py）详细日志桥接：将其 DETAILED_LOG_FILE 指向本模块 LOG_FILE
# 方案B：统一使用本文件作为唯一 detailed 日志落盘。

def attach_external_detailed_log(external_logger_module) -> None:
    """将外部 logger 模块的详细日志文件句柄绑定到当前 LOG_FILE。

    external_logger_module 需要具备：
    - DETAILED_LOG_FILE 全局变量
    - LOG_MODE 全局变量（可选）
    """
    global LOG_FILE, LOG_MODE
    if LOG_FILE is None:
        return
    try:
        if hasattr(external_logger_module, "DETAILED_LOG_FILE"):
            setattr(external_logger_module, "DETAILED_LOG_FILE", LOG_FILE)
        if hasattr(external_logger_module, "LOG_MODE"):
            setattr(external_logger_module, "LOG_MODE", LOG_MODE)
    except Exception:
        # 不中断主流程
        return

# 全局日志变量与锁（线程安全）
LOG_FILE: Optional[object] = None
LOG_MODE: str = "detailed"  # simple 或 detailed
log_lock = threading.Lock()


def init_log_file(
    log_dir: str,
    input_file: str,
    model_name: str,
    profile: str,
    n_runs: int,
    threshold: int,
    workers: int,
    hard_output: str,
    other_output: str,
    log_mode: str = "detailed"
) -> str:
    """
    初始化日志文件，返回日志路径
    
    Args:
        log_mode: 日志模式，"simple" 或 "detailed"
    """
    global LOG_FILE, LOG_MODE
    LOG_MODE = log_mode.lower()

    # 创建日志目录
    if not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    # 生成日志文件名（包含运行参数和时间戳）
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    input_basename = os.path.basename(input_file)
    if "." in input_basename:
        input_name = os.path.splitext(input_basename)[0]
    else:
        input_name = input_basename
    log_filename = f"multi_answer_filter_{timestamp}_{input_name}.log"

    log_path = os.path.join(log_dir, log_filename)

    # 打开日志文件（覆盖写入）
    LOG_FILE = open(log_path, "w", encoding="utf-8")

    # 写入运行参数
    LOG_FILE.write("=" * 80 + "\n")
    LOG_FILE.write("📋 多次回答筛题运行参数\n")
    LOG_FILE.write("=" * 80 + "\n")
    LOG_FILE.write(f"运行时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    LOG_FILE.write(f"输入文件: {input_file}\n")
    LOG_FILE.write(f"模型名称: {model_name}\n")
    LOG_FILE.write(f"用户画像: {profile}\n")
    LOG_FILE.write(f"重复次数: {n_runs}\n")
    LOG_FILE.write(f"阈值: {threshold}\n")
    LOG_FILE.write(f"并行workers: {workers}\n")
    LOG_FILE.write(f"hard输出文件: {hard_output}\n")
    LOG_FILE.write(f"other输出文件: {other_output}\n")
    LOG_FILE.write("=" * 80 + "\n")
    LOG_FILE.write("\n")
    LOG_FILE.flush()

    return log_path


def log_question_start(question_id: str, question_num: int, total_questions: int, is_multi_round: bool, question_preview: str = ""):
    """
    记录问题开始处理（用于标识日志顺序）
    """
    global LOG_FILE, LOG_MODE
    if LOG_FILE is None or getattr(LOG_FILE, "closed", False):
        return
    
    with log_lock:
        try:
            if LOG_FILE is None or getattr(LOG_FILE, "closed", False):
                return
            LOG_FILE.write("\n" + "=" * 80 + "\n")
            LOG_FILE.write(f"📌 问题 #{question_num}/{total_questions} - question_id: {question_id}\n")
            if is_multi_round:
                LOG_FILE.write("类型: 多轮问题\n")
            else:
                LOG_FILE.write("类型: 单轮问题\n")
            if question_preview:
                LOG_FILE.write(f"问题预览: {question_preview[:200]}...\n" if len(question_preview) > 200 else f"问题预览: {question_preview}\n")
            LOG_FILE.write("=" * 80 + "\n")
            LOG_FILE.flush()
        except Exception:
            return


def log_run_attempt(question_id: str, question_num: int, run_index: int, n_runs: int, is_correct: bool):
    """
    记录单次回答尝试
    """
    global LOG_FILE, LOG_MODE
    if LOG_FILE is None or getattr(LOG_FILE, "closed", False) or LOG_MODE != "detailed":
        return
    
    with log_lock:
        try:
            if LOG_FILE is None or getattr(LOG_FILE, "closed", False):
                return
            LOG_FILE.write("-" * 80 + "\n")
            LOG_FILE.write(f"🔄 第 {run_index}/{n_runs} 次回答 - question_id: {question_id}\n")
            LOG_FILE.write(f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            LOG_FILE.write(f"结果: {'✓ 正确' if is_correct else '✗ 错误'}\n")
            LOG_FILE.write("-" * 80 + "\n")
            LOG_FILE.flush()
        except Exception:
            return


def log_single_round_response(
    question_id: str,
    question_num: int,
    run_index: int,
    round_key: str,
    round_num: int,
    prompt: str,
    raw_response: Optional[Dict[str, Any]],
    judge_response: Optional[Dict[str, Any]] = None,
    model_answer: str = "",
    extracted_answer: str = "",
    is_correct: bool = False,
    judge_reasoning: str = ""
):
    """
    记录多轮题目中单轮的详细响应信息
    """
    global LOG_FILE, LOG_MODE
    if LOG_FILE is None or LOG_MODE != "detailed":
        return
    
    with log_lock:
        try:
            LOG_FILE.write("-" * 80 + "\n")
            LOG_FILE.write(f"📝 第 {run_index} 次回答 - 轮次 {round_num} ({round_key}) - question_id: {question_id}\n")
            LOG_FILE.write(f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            LOG_FILE.write("-" * 80 + "\n")
            
            # 记录提示词
            if prompt:
                LOG_FILE.write("📋 提示词:\n")
                LOG_FILE.write("-" * 80 + "\n")
                LOG_FILE.write(prompt)
                LOG_FILE.write("\n")
                LOG_FILE.write("-" * 80 + "\n")
            
            # 记录原始响应对象
            if raw_response:
                LOG_FILE.write("📦 完整原始响应对象 (raw_response):\n")
                LOG_FILE.write("-" * 80 + "\n")
                try:
                    LOG_FILE.write(json.dumps(raw_response, indent=2, ensure_ascii=False, default=str))
                    LOG_FILE.write("\n")
                except Exception as e:
                    LOG_FILE.write(f"⚠️ 无法序列化原始响应对象: {e}\n")
                    LOG_FILE.write(f"响应对象字符串: {str(raw_response)[:500]}...\n")
                LOG_FILE.write("-" * 80 + "\n")
            else:
                LOG_FILE.write("⚠️ 无原始响应对象\n")
            
            # 记录裁判模型的完整响应对象
            if judge_response:
                LOG_FILE.write("⚖️ 完整裁判模型响应对象 (judge_response):\n")
                LOG_FILE.write("-" * 80 + "\n")
                try:
                    LOG_FILE.write(json.dumps(judge_response, indent=2, ensure_ascii=False, default=str))
                    LOG_FILE.write("\n")
                except Exception as e:
                    LOG_FILE.write(f"⚠️ 无法序列化裁判响应对象: {e}\n")
                    LOG_FILE.write(f"响应对象字符串: {str(judge_response)[:500]}...\n")
                LOG_FILE.write("-" * 80 + "\n")
            
            # 记录模型答案
            if model_answer:
                LOG_FILE.write(f"💬 模型答案: {model_answer}\n")
            if extracted_answer:
                LOG_FILE.write(f"📤 提取的答案: {extracted_answer}\n")
            if judge_reasoning:
                LOG_FILE.write(f"⚖️ 裁判理由: {judge_reasoning}\n")
            LOG_FILE.write(f"结果: {'✓ 正确' if is_correct else '✗ 错误'}\n")
            
            LOG_FILE.write("=" * 80 + "\n")
            LOG_FILE.write("\n")
            LOG_FILE.flush()
        except Exception as e:
            print(f"⚠️ 写入单轮响应日志失败: {e}")


def log_single_round_response_simple(
    question_id: str,
    question_num: int,
    run_index: int,
    prompt: str,
    raw_response: Optional[Dict[str, Any]],
    judge_response: Optional[Dict[str, Any]] = None,
    model_answer: str = "",
    extracted_answer: str = "",
    is_correct: bool = False,
    judge_reasoning: str = ""
):
    """
    记录单轮题目的详细响应信息
    """
    global LOG_FILE, LOG_MODE
    if LOG_FILE is None or LOG_MODE != "detailed":
        return
    
    with log_lock:
        try:
            LOG_FILE.write("-" * 80 + "\n")
            LOG_FILE.write(f"📝 第 {run_index} 次回答 - question_id: {question_id}\n")
            LOG_FILE.write(f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            LOG_FILE.write("-" * 80 + "\n")
            
            # 记录提示词
            if prompt:
                LOG_FILE.write("📋 提示词:\n")
                LOG_FILE.write("-" * 80 + "\n")
                LOG_FILE.write(prompt)
                LOG_FILE.write("\n")
                LOG_FILE.write("-" * 80 + "\n")
            
            # 记录原始响应对象
            if raw_response:
                LOG_FILE.write("📦 完整原始响应对象 (raw_response):\n")
                LOG_FILE.write("-" * 80 + "\n")
                try:
                    LOG_FILE.write(json.dumps(raw_response, indent=2, ensure_ascii=False, default=str))
                    LOG_FILE.write("\n")
                except Exception as e:
                    LOG_FILE.write(f"⚠️ 无法序列化原始响应对象: {e}\n")
                    LOG_FILE.write(f"响应对象字符串: {str(raw_response)[:500]}...\n")
                LOG_FILE.write("-" * 80 + "\n")
            else:
                LOG_FILE.write("⚠️ 无原始响应对象\n")
            
            # 记录模型答案
            if model_answer:
                LOG_FILE.write(f"💬 模型答案: {model_answer}\n")
            if extracted_answer:
                LOG_FILE.write(f"📤 提取的答案: {extracted_answer}\n")
            if judge_reasoning:
                LOG_FILE.write(f"⚖️ 裁判理由: {judge_reasoning}\n")
            LOG_FILE.write(f"结果: {'✓ 正确' if is_correct else '✗ 错误'}\n")
            
            LOG_FILE.write("=" * 80 + "\n")
            LOG_FILE.write("\n")
            LOG_FILE.flush()
        except Exception as e:
            print(f"⚠️ 写入单轮响应日志失败: {e}")


def log_question_summary(question_id: str, question_num: int, correct_count: int, n_runs: int, threshold: int):
    """
    记录问题处理总结
    """
    global LOG_FILE
    if LOG_FILE is None or getattr(LOG_FILE, "closed", False):
        return
    
    with log_lock:
        try:
            if LOG_FILE is None or getattr(LOG_FILE, "closed", False):
                return
            LOG_FILE.write("\n" + "=" * 80 + "\n")
            LOG_FILE.write(f"📊 问题 #{question_num} 总结 - question_id: {question_id}\n")
            LOG_FILE.write(f"正确次数: {correct_count}/{n_runs}\n")
            LOG_FILE.write(f"阈值: {threshold}\n")
            category = "hard" if correct_count <= threshold else "other"
            LOG_FILE.write(f"分类: {category}\n")
            LOG_FILE.write("=" * 80 + "\n")
            LOG_FILE.write("\n")
            LOG_FILE.flush()
        except Exception:
            return


def log_stats(stats_text: str):
    """
    记录统计信息到日志
    """
    global LOG_FILE
    if LOG_FILE is None or getattr(LOG_FILE, "closed", False):
        return
    
    with log_lock:
        try:
            if LOG_FILE is None or getattr(LOG_FILE, "closed", False):
                return
            LOG_FILE.write("\n" + "=" * 80 + "\n")
            LOG_FILE.write("📊 运行统计\n")
            LOG_FILE.write("=" * 80 + "\n")
            LOG_FILE.write(stats_text)
            LOG_FILE.write("\n" + "=" * 80 + "\n")
            LOG_FILE.flush()
        except Exception:
            # 并行模式下避免刷屏
            return


def close_log_file():
    """
    关闭日志文件
    """
    global LOG_FILE
    if LOG_FILE:
        with log_lock:
            try:
                LOG_FILE.write("=" * 80 + "\n")
                LOG_FILE.write(f"日志结束时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                LOG_FILE.write("=" * 80 + "\n")
                LOG_FILE.close()
                LOG_FILE = None
            except Exception:
                LOG_FILE = None
