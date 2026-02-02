"""
模块2日志工具：
- 统一管理日志文件（module2_logs 下）
- 提供初始化、记录模型响应、关闭日志的函数
"""
import os
import time
import json
import threading
from typing import Optional

# 全局日志变量与锁（线程安全）
LOG_FILE: Optional[object] = None
log_lock = threading.Lock()

# 日志优化：计数器，控制完整显示的日志数量
_log_full_display_count = {"model": 0, "judge": 0}  # 分别计数模型和裁判的完整显示次数
_LOG_FULL_DISPLAY_LIMIT = 3  # 前N个完整显示，之后显示摘要


def init_log_file(log_dir: str, input_file: str, output_file: str, max_workers: int, batch_size: int, debug_mode: bool) -> str:
    """
    初始化日志文件，返回日志路径
    """
    global LOG_FILE, _log_full_display_count
    
    # 重置日志计数器
    _log_full_display_count = {"model": 0, "judge": 0}

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
    log_filename = f"{timestamp}_{input_name}.log"

    log_path = os.path.join(log_dir, log_filename)

    # 打开日志文件（覆盖写入）
    LOG_FILE = open(log_path, "w", encoding="utf-8")

    # 写入运行参数
    LOG_FILE.write("=" * 80 + "\n")
    LOG_FILE.write("📋 模块2运行参数\n")
    LOG_FILE.write("=" * 80 + "\n")
    LOG_FILE.write(f"运行时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    LOG_FILE.write(f"输入文件: {input_file}\n")
    LOG_FILE.write(f"输出文件: {output_file}\n")
    LOG_FILE.write(f"并发线程数: {max_workers}\n")
    LOG_FILE.write(f"批量保存大小: {batch_size}\n")
    LOG_FILE.write(f"调试模式: {debug_mode}\n")
    LOG_FILE.write(f"日志优化: 提示词前 {_LOG_FULL_DISPLAY_LIMIT} 条完整显示，后续显示摘要；响应对象始终完整\n")
    LOG_FILE.write("=" * 80 + "\n")
    LOG_FILE.write("\n")
    LOG_FILE.flush()

    return log_path


def log_question_start(question_id: str, question_num: int, is_multi_round: bool, question_preview: str = ""):
    """
    记录问题开始处理（用于标识日志顺序）
    """
    global LOG_FILE
    if LOG_FILE is None:
        return
    
    with log_lock:
        try:
            LOG_FILE.write("\n" + "=" * 80 + "\n")
            LOG_FILE.write(f"📌 问题 #{question_num} - question_id: {question_id}\n")
            if is_multi_round:
                LOG_FILE.write(f"类型: 多轮问题\n")
            else:
                LOG_FILE.write(f"类型: 单轮问题\n")
            if question_preview:
                LOG_FILE.write(f"问题预览: {question_preview}\n")
            LOG_FILE.write("=" * 80 + "\n")
            LOG_FILE.flush()
        except Exception as e:
            print(f"⚠️ 写入问题开始日志失败: {e}")


def log_model_response(question_id: str, question_num: int, model_num: int, model_name: str, response, prompt: str = ""):
    """
    记录单个模型的原始响应
    优化：前N个完整显示，后续显示摘要
    """
    global LOG_FILE, _log_full_display_count, _LOG_FULL_DISPLAY_LIMIT
    if LOG_FILE is None:
        return

    with log_lock:
        try:
            # 判断是否完整显示
            _log_full_display_count["model"] += 1
            is_full_display = _log_full_display_count["model"] <= _LOG_FULL_DISPLAY_LIMIT
            
            LOG_FILE.write("-" * 80 + "\n")
            LOG_FILE.write(f"📝 模型{model_num} ({model_name}) - question_id: {question_id}\n")
            LOG_FILE.write(f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            LOG_FILE.write("-" * 80 + "\n")

            # 记录提示词（前N个完整显示，后续只显示摘要）
            if prompt:
                if is_full_display:
                    LOG_FILE.write("📋 最终提交给模型的完整提示词:\n")
                    LOG_FILE.write("-" * 80 + "\n")
                    LOG_FILE.write(prompt)
                    LOG_FILE.write("\n")
                    LOG_FILE.write("-" * 80 + "\n")
                else:
                    # 省略版：只显示前200字符和总长度
                    prompt_preview = prompt[:200] + "..." if len(prompt) > 200 else prompt
                    LOG_FILE.write(f"📋 提示词摘要（完整长度: {len(prompt)} 字符）:\n")
                    LOG_FILE.write("-" * 80 + "\n")
                    LOG_FILE.write(prompt_preview)
                    LOG_FILE.write("\n")
                    LOG_FILE.write("-" * 80 + "\n")

            # 记录响应对象
            try:
                if hasattr(response, "model_dump"):
                    response_dict = response.model_dump()
                elif isinstance(response, dict):
                    response_dict = response
                else:
                    # 尝试手动构建字典
                    response_dict = {
                        "id": getattr(response, "id", None),
                        "object": getattr(response, "object", None),
                        "created": getattr(response, "created", None),
                        "model": getattr(response, "model", None),
                    }
                    if hasattr(response, "choices") and len(response.choices) > 0:
                        choice = response.choices[0]
                        choice_dict = {
                            "index": getattr(choice, "index", None),
                            "finish_reason": getattr(choice, "finish_reason", None),
                        }
                        if hasattr(choice, "message"):
                            message = choice.message
                            message_dict = {
                                "role": getattr(message, "role", None),
                                "content": getattr(message, "content", None),
                            }
                            # 详细日志模式下：保留所有reasoning字段，不按优先级过滤
                            if hasattr(message, "reasoning") and getattr(message, "reasoning", None):
                                message_dict["reasoning"] = message.reasoning
                            if hasattr(message, "reasoning_content") and getattr(message, "reasoning_content", None):
                                message_dict["reasoning_content"] = message.reasoning_content
                            if hasattr(message, "reasoning_details") and getattr(message, "reasoning_details", None):
                                message_dict["reasoning_details"] = message.reasoning_details
                            choice_dict["message"] = message_dict
                        response_dict["choices"] = [choice_dict]

                # 响应对象：详细模式下必须完全完整，不能简化
                LOG_FILE.write("完整响应对象:\n")
                LOG_FILE.write(json.dumps(response_dict, indent=2, ensure_ascii=False, default=str))
                LOG_FILE.write("\n")
            except Exception as e:
                LOG_FILE.write(f"⚠️ 无法序列化响应对象: {e}\n")
                LOG_FILE.write(f"响应对象字符串: {str(response)}\n")

            LOG_FILE.write("=" * 80 + "\n")
            LOG_FILE.write("\n")
            LOG_FILE.flush()
        except Exception as e:
            # 日志失败不能影响主流程
            print(f"⚠️ 写入日志失败: {e}")


def log_judge_response(question_id: str, model_key: str, model_answer: str, 
                       gt_answer: str, is_match: bool, judge_reasoning: str, judge_time: float,
                       raw_response_json, prompt: str = "", round_key: str = None):
    """
    记录裁判模型的响应
    优化：裁判提示词简化显示（因为每次都差不多），响应对象前N个完整显示
    
    Args:
        question_id: 问题ID
        model_key: 被评判的模型键（model1/model2/model3）
        model_answer: 模型答案
        gt_answer: 标准答案
        is_match: 是否匹配
        judge_reasoning: 评判理由
        judge_time: 评判耗时
        raw_response_json: 原始API响应（字典格式）
        prompt: 最终提交给裁判模型的完整提示词
        round_key: 轮次键（多轮问题时使用，如 "round1"）
    """
    global LOG_FILE, _log_full_display_count, _LOG_FULL_DISPLAY_LIMIT
    if LOG_FILE is None:
        return
    
    with log_lock:
        try:
            # 判断是否完整显示响应对象（裁判提示词始终简化）
            _log_full_display_count["judge"] += 1
            is_full_display_response = _log_full_display_count["judge"] <= _LOG_FULL_DISPLAY_LIMIT
            
            LOG_FILE.write("-" * 80 + "\n")
            if round_key:
                LOG_FILE.write(f"⚖️ 裁判模型 - {model_key} ({round_key}) - question_id: {question_id}\n")
            else:
                LOG_FILE.write(f"⚖️ 裁判模型 - {model_key} - question_id: {question_id}\n")
            LOG_FILE.write(f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            LOG_FILE.write("-" * 80 + "\n")
            
            # 记录评判信息
            LOG_FILE.write(f"模型答案: {model_answer}\n")
            LOG_FILE.write(f"标准答案: {gt_answer}\n")
            LOG_FILE.write(f"评判结果: {'✅ 一致' if is_match else '❌ 不一致'}\n")
            LOG_FILE.write(f"评判理由: {judge_reasoning}\n")
            LOG_FILE.write(f"耗时: {judge_time:.2f}秒\n")
            LOG_FILE.write("-" * 80 + "\n")
            
            # 裁判提示词简化显示（因为每次都差不多，只显示长度和摘要）
            if prompt:
                prompt_preview = prompt[:150] + "..." if len(prompt) > 150 else prompt
                LOG_FILE.write(f"📋 裁判提示词摘要（完整长度: {len(prompt)} 字符，内容大同小异，已省略）:\n")
                LOG_FILE.write("-" * 80 + "\n")
                LOG_FILE.write(prompt_preview)
                LOG_FILE.write("\n")
                LOG_FILE.write("-" * 80 + "\n")
            
            # 记录响应对象（前N个完整显示，后续省略）
            if raw_response_json:
                try:
                    if is_full_display_response:
                        LOG_FILE.write("完整响应对象:\n")
                        LOG_FILE.write(json.dumps(raw_response_json, indent=2, ensure_ascii=False, default=str))
                        LOG_FILE.write("\n")
                    else:
                        # 省略版：只显示关键字段
                        simplified_response = {
                            "id": raw_response_json.get("id"),
                            "model": raw_response_json.get("model"),
                            "choices": raw_response_json.get("choices", [])[:1] if raw_response_json.get("choices") else [],
                            "usage": raw_response_json.get("usage"),
                        }
                        LOG_FILE.write("响应对象摘要（已省略完整内容）:\n")
                        LOG_FILE.write(json.dumps(simplified_response, indent=2, ensure_ascii=False, default=str))
                        LOG_FILE.write("\n")
                except Exception as e:
                    LOG_FILE.write(f"⚠️ 无法序列化响应对象: {e}\n")
                    LOG_FILE.write(f"响应对象字符串: {str(raw_response_json)}\n")
            else:
                LOG_FILE.write("⚠️ 无原始响应对象（可能使用了降级策略）\n")
            
            LOG_FILE.write("=" * 80 + "\n")
            LOG_FILE.write("\n")
            LOG_FILE.flush()
        except Exception as e:
            # 日志失败不能影响主流程
            print(f"⚠️ 写入裁判模型日志失败: {e}")


def log_stats(stats_text: str):
    """
    记录评估统计信息到日志
    """
    global LOG_FILE
    if LOG_FILE is None:
        return
    
    with log_lock:
        try:
            LOG_FILE.write("\n" + "=" * 80 + "\n")
            LOG_FILE.write("📊 评估统计\n")
            LOG_FILE.write("=" * 80 + "\n")
            LOG_FILE.write(stats_text)
            LOG_FILE.write("\n" + "=" * 80 + "\n")
            LOG_FILE.flush()
        except Exception as e:
            print(f"⚠️ 写入统计日志失败: {e}")


def log_output_info(out_dir: str):
    """
    记录输出文件信息到日志
    """
    global LOG_FILE
    if LOG_FILE is None:
        return
    
    with log_lock:
        try:
            import os
            LOG_FILE.write("\n" + "=" * 80 + "\n")
            LOG_FILE.write("📁 输出文件信息\n")
            LOG_FILE.write("=" * 80 + "\n")
            LOG_FILE.write(f"输出目录: {os.path.abspath(out_dir)}\n")
            LOG_FILE.write(f"包含文件: L1.json, L2.json, L3.json, L4.json, summary.json\n")
            LOG_FILE.write("=" * 80 + "\n")
            LOG_FILE.flush()
        except Exception as e:
            print(f"⚠️ 写入输出信息日志失败: {e}")


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


