"""
日志记录模块
负责详细日志的写入和管理
"""
import json
import logging
import threading
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

# 全局变量：用于详细日志记录
DETAILED_LOG_FILE = None
LOG_MODE = "detailed"
log_lock = threading.Lock()  # 日志文件写入锁

# 日志优化：计数器，控制完整显示的日志数量
_log_full_display_count = {"model": 0, "judge": 0}  # 分别计数模型和裁判的完整显示次数
_LOG_FULL_DISPLAY_LIMIT = 3  # 前N个完整显示，之后显示摘要


def sanitize_messages_for_log(messages: List[Dict[str, Any]], image_paths: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    清理messages中的base64图片数据，用于日志记录
    将base64编码的图片数据替换为图片路径信息，不打印完整的image_url
    
    Args:
        messages: 原始messages列表
        image_paths: 图片路径列表（可选），用于替换base64数据
        
    Returns:
        清理后的messages列表
    """
    if not messages:
        return messages
    
    # 如果没有提供image_paths，尝试从messages中提取URL路径
    image_paths = image_paths or []
    image_path_index = 0
    
    sanitized = []
    for msg in messages:
        sanitized_msg = msg.copy()
        content = msg.get("content", [])
        
        # 如果content是列表（可能包含图片）
        if isinstance(content, list):
            sanitized_content = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "image_url":
                    image_url = item.get("image_url", {}).get("url", "")
                    # 如果是base64编码的图片，替换为image_path
                    if image_url.startswith("data:image/"):
                        # 优先使用提供的image_paths
                        if image_path_index < len(image_paths):
                            image_path = image_paths[image_path_index]
                            sanitized_content.append({
                                "type": "image_path",
                                "image_path": image_path
                            })
                            image_path_index += 1
                        else:
                            # 如果没有提供image_paths，使用占位符
                            format_match = image_url.split(";")[0].replace("data:image/", "")
                            sanitized_content.append({
                                "type": "image_path",
                                "image_path": f"[BASE64_IMAGE_DATA_REMOVED - format: {format_match}]"
                            })
                    else:
                        # 如果是URL或路径，直接作为image_path记录
                        sanitized_content.append({
                            "type": "image_path",
                            "image_path": image_url
                        })
                else:
                    # 非图片内容，保留原样
                    sanitized_content.append(item)
            sanitized_msg["content"] = sanitized_content
        # 如果content是字符串，直接保留
        elif isinstance(content, str):
            sanitized_msg["content"] = content
        
        sanitized.append(sanitized_msg)
    
    return sanitized


def log_model_response_detailed(
    question_id: str,
    model_name: str,
    profile: str,
    prompt: str,
    raw_response: Dict[str, Any],
    round_key: Optional[str] = None,
    image_paths: Optional[List[str]] = None
):
    """
    记录模型响应的详细日志（参考 module2/logger.py）
    优化：前N个完整显示，后续只显示摘要
    
    Args:
        question_id: 问题ID
        model_name: 模型名称
        profile: 用户画像
        prompt: 完整提示词
        raw_response: 原始API响应
        round_key: 轮次键（多轮问题时使用）
        image_paths: 图片路径列表（可选）
    """
    global DETAILED_LOG_FILE, _log_full_display_count, _LOG_FULL_DISPLAY_LIMIT
    if DETAILED_LOG_FILE is None:
        return
    
    with log_lock:
        try:
            # 判断是否完整显示
            _log_full_display_count["model"] += 1
            is_full_display = _log_full_display_count["model"] <= _LOG_FULL_DISPLAY_LIMIT
            
            DETAILED_LOG_FILE.write("-" * 80 + "\n")
            if round_key:
                DETAILED_LOG_FILE.write(f"📝 模型响应 - {model_name} ({profile}) - {round_key} - question_id: {question_id}\n")
            else:
                DETAILED_LOG_FILE.write(f"📝 模型响应 - {model_name} ({profile}) - question_id: {question_id}\n")
            DETAILED_LOG_FILE.write(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            
            # 记录图片路径信息（如果有）
            if image_paths:
                DETAILED_LOG_FILE.write(f"图片路径: {', '.join(image_paths)}\n")
            
            DETAILED_LOG_FILE.write("-" * 80 + "\n")
            
            # 记录提示词（前N个完整显示，后续只显示摘要）
            if prompt:
                if is_full_display:
                    DETAILED_LOG_FILE.write("📋 最终提交给模型的完整提示词:\n")
                    DETAILED_LOG_FILE.write("-" * 80 + "\n")
                    DETAILED_LOG_FILE.write(prompt)
                    DETAILED_LOG_FILE.write("\n")
                    DETAILED_LOG_FILE.write("-" * 80 + "\n")
                else:
                    # 省略版：只显示前200字符和总长度
                    prompt_preview = prompt[:200] + "..." if len(prompt) > 200 else prompt
                    DETAILED_LOG_FILE.write(f"📋 提示词摘要（完整长度: {len(prompt)} 字符）:\n")
                    DETAILED_LOG_FILE.write("-" * 80 + "\n")
                    DETAILED_LOG_FILE.write(prompt_preview)
                    DETAILED_LOG_FILE.write("\n")
                    DETAILED_LOG_FILE.write("-" * 80 + "\n")
            
            # 记录完整响应对象（详细日志模式下必须完全完整，包含所有reasoning字段）
            if raw_response:
                DETAILED_LOG_FILE.write("完整响应对象:\n")
                # 详细日志模式下，确保所有reasoning字段都保留（不从raw_response中过滤）
                # raw_response可能已经按优先级过滤过，但日志中我们需要完整显示
                # 如果raw_response是字典且已经过滤，我们需要尝试从原始响应中获取所有字段
                DETAILED_LOG_FILE.write(json.dumps(raw_response, indent=2, ensure_ascii=False, default=str))
                DETAILED_LOG_FILE.write("\n")
            else:
                DETAILED_LOG_FILE.write("⚠️ 无原始响应对象\n")
            
            DETAILED_LOG_FILE.write("=" * 80 + "\n\n")
            DETAILED_LOG_FILE.flush()
        except Exception as e:
            logging.warning(f"写入模型响应详细日志失败: {e}")


def log_judge_response_detailed(
    question_id: str,
    model_name: str,
    profile: str,
    model_answer: str,
    gt_answer: str,
    is_match: bool,
    reasoning: str,
    judge_time: float,
    raw_response: Optional[Dict[str, Any]],
    prompt: str = "",
    round_key: Optional[str] = None,
    image_paths: Optional[List[str]] = None
):
    """
    记录裁判模型响应的详细日志（参考 module2/logger.py）
    优化：裁判提示词简化显示（因为每次都差不多），只显示关键信息
    
    Args:
        question_id: 问题ID
        model_name: 被评判的模型名称
        profile: 用户画像
        model_answer: 模型答案
        gt_answer: 标准答案
        is_match: 是否匹配
        reasoning: 评判理由
        judge_time: 评判耗时
        raw_response: 原始API响应
        prompt: 最终提交给裁判模型的完整提示词
        round_key: 轮次键（多轮问题时使用）
        image_paths: 图片路径列表（可选）
    """
    global DETAILED_LOG_FILE, _log_full_display_count, _LOG_FULL_DISPLAY_LIMIT
    if DETAILED_LOG_FILE is None:
        return
    
    with log_lock:
        try:
            # 判断是否完整显示（裁判提示词始终简化，但响应对象前N个完整显示）
            _log_full_display_count["judge"] += 1
            is_full_display_response = _log_full_display_count["judge"] <= _LOG_FULL_DISPLAY_LIMIT
            
            DETAILED_LOG_FILE.write("-" * 80 + "\n")
            if round_key:
                DETAILED_LOG_FILE.write(f"⚖️ 裁判模型 - {model_name} ({profile}) - {round_key} - question_id: {question_id}\n")
            else:
                DETAILED_LOG_FILE.write(f"⚖️ 裁判模型 - {model_name} ({profile}) - question_id: {question_id}\n")
            DETAILED_LOG_FILE.write(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            
            # 记录图片路径信息（如果有）
            if image_paths:
                DETAILED_LOG_FILE.write(f"图片路径: {', '.join(image_paths)}\n")
            
            DETAILED_LOG_FILE.write("-" * 80 + "\n")
            
            # 记录评判信息
            DETAILED_LOG_FILE.write(f"模型答案: {model_answer}\n")
            DETAILED_LOG_FILE.write(f"标准答案: {gt_answer}\n")
            DETAILED_LOG_FILE.write(f"评判结果: {'✅ 一致' if is_match else '❌ 不一致'}\n")
            DETAILED_LOG_FILE.write(f"评判理由: {reasoning}\n")
            DETAILED_LOG_FILE.write(f"耗时: {judge_time:.2f}秒\n")
            DETAILED_LOG_FILE.write("-" * 80 + "\n")
            
            # 裁判提示词简化显示（因为每次都差不多，只显示长度和摘要）
            if prompt:
                prompt_preview = prompt[:150] + "..." if len(prompt) > 150 else prompt
                DETAILED_LOG_FILE.write(f"📋 裁判提示词摘要（完整长度: {len(prompt)} 字符，内容大同小异，已省略）:\n")
                DETAILED_LOG_FILE.write("-" * 80 + "\n")
                DETAILED_LOG_FILE.write(prompt_preview)
                DETAILED_LOG_FILE.write("\n")
                DETAILED_LOG_FILE.write("-" * 80 + "\n")
            
            # 记录完整响应对象（前N个完整显示，后续省略）
            if raw_response:
                if is_full_display_response:
                    DETAILED_LOG_FILE.write("完整响应对象:\n")
                    DETAILED_LOG_FILE.write(json.dumps(raw_response, indent=2, ensure_ascii=False, default=str))
                    DETAILED_LOG_FILE.write("\n")
                else:
                    # 省略版：只显示关键字段
                    simplified_response = {
                        "id": raw_response.get("id"),
                        "model": raw_response.get("model"),
                        "choices": raw_response.get("choices", [])[:1] if raw_response.get("choices") else [],
                        "usage": raw_response.get("usage"),
                    }
                    DETAILED_LOG_FILE.write("响应对象摘要（已省略完整内容）:\n")
                    DETAILED_LOG_FILE.write(json.dumps(simplified_response, indent=2, ensure_ascii=False, default=str))
                    DETAILED_LOG_FILE.write("\n")
            else:
                DETAILED_LOG_FILE.write("⚠️ 无原始响应对象\n")
            
            DETAILED_LOG_FILE.write("=" * 80 + "\n\n")
            DETAILED_LOG_FILE.flush()
        except Exception as e:
            logging.warning(f"写入裁判模型详细日志失败: {e}")


def setup_logging(log_dir: str, log_level: str = "INFO", log_mode: str = "detailed"):
    """
    配置日志记录器
    
    Args:
        log_dir: 日志目录
        log_level: 日志级别（DEBUG/INFO/WARNING/ERROR）
        log_mode: 日志模式（simple/detailed）
    """
    global DETAILED_LOG_FILE, LOG_MODE, _log_full_display_count
    
    LOG_MODE = log_mode.lower()
    # 重置日志计数器
    _log_full_display_count = {"model": 0, "judge": 0}
    
    log_dir = Path(log_dir)
    log_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = log_dir / f'eval_{timestamp}.log'
    
    # 根据日志模式选择不同的格式
    if LOG_MODE == "simple":
        # 简化模式：只显示级别和消息
        log_format = '%(levelname)s - %(message)s'
        logging.info(f"日志模式: {log_mode} (简化模式)")
    else:
        # 详细模式：显示时间、级别和消息
        log_format = '%(asctime)s - %(levelname)s - %(message)s'
        # 打开详细日志文件（用于记录完整响应）
        try:
            DETAILED_LOG_FILE = open(log_file, 'w', encoding='utf-8')
            DETAILED_LOG_FILE.write("=" * 80 + "\n")
            DETAILED_LOG_FILE.write("📋 评测详细日志\n")
            DETAILED_LOG_FILE.write("=" * 80 + "\n")
            DETAILED_LOG_FILE.write(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            DETAILED_LOG_FILE.write(f"日志模式: {log_mode}\n")
            DETAILED_LOG_FILE.write(f"日志优化: 提示词前 {_LOG_FULL_DISPLAY_LIMIT} 条完整显示，后续显示摘要；响应对象始终完整\n")
            DETAILED_LOG_FILE.write("=" * 80 + "\n\n")
            DETAILED_LOG_FILE.flush()
            logging.info(f"日志模式: {log_mode} (详细模式，详细日志文件: {log_file})")
        except Exception as e:
            logging.error(f"无法创建详细日志文件 {log_file}: {e}")
            DETAILED_LOG_FILE = None
    
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format=log_format,
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(str(log_file), encoding='utf-8')
        ],
        force=True
    )
    logging.info(f"日志记录器初始化成功 (模式: {log_mode})")


def get_detailed_log_file():
    """获取详细日志文件句柄"""
    return DETAILED_LOG_FILE


def get_log_mode():
    """获取当前日志模式"""
    # 方案B：由调用方统一管理详细日志文件；evaluate 侧不再依赖 DETAILED_LOG_FILE。
    # 这里仍保留 LOG_MODE 作为开关，但不要据此打印“已启用但文件为None”的警告。
    return LOG_MODE


def is_detailed_log_enabled() -> bool:
    """是否启用 detailed 日志（且具备可写入的详细日志文件）。"""
    return LOG_MODE == "detailed" and DETAILED_LOG_FILE is not None


def close_detailed_log_file():
    """关闭详细日志文件"""
    global DETAILED_LOG_FILE
    if DETAILED_LOG_FILE:
        with log_lock:
            try:
                DETAILED_LOG_FILE.write("=" * 80 + "\n")
                DETAILED_LOG_FILE.write(f"日志结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                DETAILED_LOG_FILE.write("=" * 80 + "\n")
                DETAILED_LOG_FILE.close()
                DETAILED_LOG_FILE = None
            except Exception as e:
                logging.warning(f"关闭详细日志文件失败: {e}")
                DETAILED_LOG_FILE = None

