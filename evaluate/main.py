"""
评测主脚本
支持多种用户画像、多种模型的评测
"""
import os
import sys
import json
import argparse
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

# 添加当前目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)
sys.path.insert(0, current_dir)

try:
    from evaluate.data_loader import load_and_validate
    from evaluate.prompts import get_prompt, get_all_profiles
    from evaluate.model_api import call_model_api, extract_answer_from_response
    from evaluate.judge import judge_answer
    from evaluate.config import MODEL_DEFINITIONS, get_eval_models, USER_PROFILES, EVAL_CONFIG
except ImportError:
    # 如果作为模块导入失败，尝试直接导入
    from data_loader import load_and_validate
    from prompts import get_prompt, get_all_profiles
    from model_api import call_model_api, extract_answer_from_response
    from judge import judge_answer
    from config import MODEL_DEFINITIONS, get_eval_models, USER_PROFILES, EVAL_CONFIG


# 全局变量：用于详细日志记录
DETAILED_LOG_FILE = None
LOG_MODE = "detailed"
log_lock = threading.Lock()  # 日志文件写入锁


def log_model_response_detailed(
    question_id: str,
    model_name: str,
    profile: str,
    prompt: str,
    raw_response: Dict[str, Any],
    round_key: Optional[str] = None
):
    """
    记录模型响应的详细日志（参考 module2/logger.py）
    
    Args:
        question_id: 问题ID
        model_name: 模型名称
        profile: 用户画像
        prompt: 完整提示词
        raw_response: 原始API响应
        round_key: 轮次键（多轮问题时使用）
    """
    global DETAILED_LOG_FILE
    if DETAILED_LOG_FILE is None:
        return
    
    with log_lock:
        try:
            DETAILED_LOG_FILE.write("-" * 80 + "\n")
            if round_key:
                DETAILED_LOG_FILE.write(f"📝 模型响应 - {model_name} ({profile}) - {round_key} - question_id: {question_id}\n")
            else:
                DETAILED_LOG_FILE.write(f"📝 模型响应 - {model_name} ({profile}) - question_id: {question_id}\n")
            DETAILED_LOG_FILE.write(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            DETAILED_LOG_FILE.write("-" * 80 + "\n")
            
            # 记录完整的最终提示词
            if prompt:
                DETAILED_LOG_FILE.write("📋 最终提交给模型的完整提示词:\n")
                DETAILED_LOG_FILE.write("-" * 80 + "\n")
                DETAILED_LOG_FILE.write(prompt)
                DETAILED_LOG_FILE.write("\n")
                DETAILED_LOG_FILE.write("-" * 80 + "\n")
            
            # 记录完整响应对象
            if raw_response:
                DETAILED_LOG_FILE.write("完整响应对象:\n")
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
    round_key: Optional[str] = None
):
    """
    记录裁判模型响应的详细日志（参考 module2/logger.py）
    
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
    """
    global DETAILED_LOG_FILE
    if DETAILED_LOG_FILE is None:
        return
    
    with log_lock:
        try:
            DETAILED_LOG_FILE.write("-" * 80 + "\n")
            if round_key:
                DETAILED_LOG_FILE.write(f"⚖️ 裁判模型 - {model_name} ({profile}) - {round_key} - question_id: {question_id}\n")
            else:
                DETAILED_LOG_FILE.write(f"⚖️ 裁判模型 - {model_name} ({profile}) - question_id: {question_id}\n")
            DETAILED_LOG_FILE.write(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            DETAILED_LOG_FILE.write("-" * 80 + "\n")
            
            # 记录评判信息
            DETAILED_LOG_FILE.write(f"模型答案: {model_answer}\n")
            DETAILED_LOG_FILE.write(f"标准答案: {gt_answer}\n")
            DETAILED_LOG_FILE.write(f"评判结果: {'✅ 一致' if is_match else '❌ 不一致'}\n")
            DETAILED_LOG_FILE.write(f"评判理由: {reasoning}\n")
            DETAILED_LOG_FILE.write(f"耗时: {judge_time:.2f}秒\n")
            DETAILED_LOG_FILE.write("-" * 80 + "\n")
            
            # 记录完整的最终提示词
            if prompt:
                DETAILED_LOG_FILE.write("📋 最终提交给裁判模型的完整提示词:\n")
                DETAILED_LOG_FILE.write("-" * 80 + "\n")
                DETAILED_LOG_FILE.write(prompt)
                DETAILED_LOG_FILE.write("\n")
                DETAILED_LOG_FILE.write("-" * 80 + "\n")
            
            # 记录完整响应对象
            if raw_response:
                DETAILED_LOG_FILE.write("完整响应对象:\n")
                DETAILED_LOG_FILE.write(json.dumps(raw_response, indent=2, ensure_ascii=False, default=str))
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
    global DETAILED_LOG_FILE, LOG_MODE
    
    LOG_MODE = log_mode.lower()
    log_dir = Path(log_dir)
    log_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = log_dir / f'eval_{timestamp}.log'
    
    # 根据日志模式选择不同的格式
    if LOG_MODE == "simple":
        # 简化模式：只显示级别和消息
        log_format = '%(levelname)s - %(message)s'
    else:
        # 详细模式：显示时间、级别和消息
        log_format = '%(asctime)s - %(levelname)s - %(message)s'
        # 打开详细日志文件（用于记录完整响应）
        DETAILED_LOG_FILE = open(log_file, 'w', encoding='utf-8')
        DETAILED_LOG_FILE.write("=" * 80 + "\n")
        DETAILED_LOG_FILE.write("📋 评测详细日志\n")
        DETAILED_LOG_FILE.write("=" * 80 + "\n")
        DETAILED_LOG_FILE.write(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        DETAILED_LOG_FILE.write(f"日志模式: {log_mode}\n")
        DETAILED_LOG_FILE.write("=" * 80 + "\n\n")
        DETAILED_LOG_FILE.flush()
    
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


def evaluate_single_item(
    item: Dict[str, Any],
    enabled_models: List[str],
    profiles: List[str],
    workers: int = 1
) -> Optional[Dict[str, Any]]:
    """
    评测单个数据项
    
    Args:
        item: 数据项
        enabled_models: 启用的模型列表
        profiles: 用户画像列表
        
    Returns:
        评测结果字典，如果失败返回 None
    """
    # 获取问题ID
    item_id = item.get("question_id") or item.get("id", "")
    
    logging.info(f"\n{'='*60}")
    logging.info(f"评测数据项: {item_id}")
    logging.info(f"{'='*60}")
    
    try:
        # 获取数据项信息
        question = item.get("question", "")
        answer = item.get("answer", "")
        options = item.get("options")
        
        # 处理image_path：支持多张图片（可能是字符串、列表或逗号分隔的字符串）
        image_path_raw = item.get("image_path", "")
        image_paths = []
        
        if image_path_raw:
            if isinstance(image_path_raw, list):
                # 已经是列表格式
                image_paths = image_path_raw
            elif isinstance(image_path_raw, str):
                # 字符串格式：可能是单个路径或逗号分隔的多个路径
                if ',' in image_path_raw:
                    # 逗号分隔的多个路径
                    image_paths = [path.strip() for path in image_path_raw.split(',') if path.strip()]
                else:
                    # 单个路径
                    image_paths = [image_path_raw] if image_path_raw.strip() else []
            else:
                # 其他类型，转换为字符串
                image_paths = [str(image_path_raw)] if image_path_raw else []
        
        # 支持image_urls字段（第二种格式）
        image_urls = item.get("image_urls", [])
        if image_urls:
            # 如果是URL，也添加到路径列表（API调用时会处理）
            if isinstance(image_urls, list):
                image_paths.extend(image_urls)
            else:
                image_paths.append(image_urls)
        
        # 去重并过滤空值
        image_paths = [path for path in image_paths if path and path.strip()]
        
        # 判断是否为多轮问答格式
        is_multi_round = item.get("is_multi_round", False)
        if not is_multi_round:
            # 检查是否为多轮格式（question和answer都是字典）
            is_multi_round = (
                isinstance(question, dict) and 
                isinstance(answer, dict) and
                any(key.startswith("round") for key in question.keys())
            )
        
        has_options = options is not None and isinstance(options, dict) and any(options.values()) if options else False
        
        # 获取并标准化题型（统一转换为中文）
        raw_question_type = item.get("question_type", "")
        normalized_question_type = ""
        if raw_question_type:
            try:
                from evaluate.prompts import normalize_question_type
                normalized_question_type = normalize_question_type(raw_question_type)
            except ImportError:
                from prompts import normalize_question_type
                normalized_question_type = normalize_question_type(raw_question_type)
        
        # 存储所有评测结果（使用标准格式字段名，题型使用中文）
        results = {
            "question_id": item_id,
            "image_id": item.get("image_id", ""),
            "image_path": image_paths[0] if image_paths else "",  # 保存第一个路径用于显示
            "image_paths": image_paths,  # 保存所有图片路径
            "image_type": item.get("image_type", ""),
            "question_type": normalized_question_type or raw_question_type,  # 使用中文题型
            "question": question,
            "answer": answer,
            "options": options,
            "is_multi_round": is_multi_round,
            "profiles": {}
        }
        
        # 保留分类字段（用于统计）
        for field in ["scenario", "capability", "difficulty", "source"]:
            if field in item:
                results[field] = item[field]
        
        # 对每个用户画像进行评测
        for profile in profiles:
            logging.info(f"\n--- 用户画像: {profile} ---")
            
            profile_results = {
                "profile": profile,
                "models": {}
            }
            
            # 处理多轮问答
            if is_multi_round:
                # 多轮问答：使用对话历史逐轮评测
                rounds_data = {}
                all_rounds_correct = True
                total_response_time = 0
                total_judge_time = 0
                
                # 获取所有轮次（按round1, round2...排序）
                round_keys = sorted(
                    [k for k in question.keys() if k.startswith("round")],
                    key=lambda x: int(x.replace("round", "")) if x.replace("round", "").isdigit() else 999
                )
                
                # 为每个模型维护对话历史（messages列表）
                # 格式：{model_name: [{"role": "user", "content": ...}, {"role": "assistant", "content": ...}, ...]}
                conversation_history = {model_name: [] for model_name in enabled_models}
                
                for round_key in round_keys:
                    round_num = round_key.replace("round", "")
                    round_question = question.get(round_key, "")
                    round_answer = answer.get(round_key, "")
                    
                    logging.info(f"  轮次 {round_num}: {round_question[:100]}...")
                    
                    # 对每个启用的模型进行评测
                    for model_name in enabled_models:
                        # model_name 直接对应 MODEL_DEFINITIONS 中的 key
                        if round_key not in rounds_data:
                            rounds_data[round_key] = {}
                        
                        try:
                            # 获取该用户画像的提示词（单轮问题，包含题型提示词）
                            prompt = get_prompt(profile, round_question, None, normalized_question_type)
                            
                            # 构建对话历史：如果是第一轮，只包含当前问题；否则包含前面的对话历史
                            messages = conversation_history[model_name].copy()
                            
                            # 添加当前轮次的问题
                            # 每轮都可以输入图片（如果需要），但通常第一轮输入即可
                            # 检查对话历史中是否已经包含图片
                            has_image_in_history = False
                            if messages:
                                for msg in messages:
                                    if msg.get("role") == "user":
                                        content = msg.get("content", [])
                                        if isinstance(content, list):
                                            for item in content:
                                                if isinstance(item, dict) and item.get("type") == "image_url":
                                                    has_image_in_history = True
                                                    break
                                        if has_image_in_history:
                                            break
                            
                            # 构建当前轮次的user消息
                            from evaluate.model_api import get_image_format, encode_image
                            user_content = []
                            
                            # 如果对话历史中没有图片，且当前有图片路径，则添加图片
                            if not has_image_in_history and image_paths:
                                for image_path in image_paths:
                                    if image_path.startswith(("http://", "https://")):
                                        user_content.append({
                                            "type": "image_url",
                                            "image_url": {"url": image_path}
                                        })
                                    elif os.path.exists(image_path):
                                        image_format = get_image_format(image_path)
                                        base64_image = encode_image(image_path)
                                        user_content.append({
                                            "type": "image_url",
                                            "image_url": {"url": f"data:image/{image_format};base64,{base64_image}"}
                                        })
                            
                            # 添加文本问题
                            user_content.append({"type": "text", "text": prompt})
                            current_user_msg = {"role": "user", "content": user_content}
                            
                            messages.append(current_user_msg)
                            
                            # 调用模型API（使用对话历史）
                            model_answer, response_time, raw_response = call_model_api(
                                model_name=model_name,
                                messages=messages
                            )
                            
                            # 提取答案（用于添加到对话历史）
                            extracted_answer, is_from_box, original_response = extract_answer_from_response(model_answer, False)
                            
                            # 将本轮问答添加到对话历史中，供下一轮使用
                            # 注意：assistant消息只保存简要答案（extracted_answer），而不是完整的回答，以减少token消耗
                            # 如果extracted_answer为空，fallback到original_response的后500字符（答案通常在结尾）
                            brief_answer_for_history = extracted_answer if extracted_answer and extracted_answer.strip() else (
                                original_response[-500:] if len(original_response) > 500 else original_response
                            )
                            
                            conversation_history[model_name].append(current_user_msg)
                            conversation_history[model_name].append({"role": "assistant", "content": brief_answer_for_history})
                            
                            # 详细日志：记录模型响应
                            # 将对话历史转换为字符串格式（用于日志）
                            prompt_for_log = json.dumps(messages, ensure_ascii=False, indent=2) if messages else prompt
                            if LOG_MODE == "detailed" and DETAILED_LOG_FILE:
                                log_model_response_detailed(
                                    question_id=item_id,
                                    round_key=round_key,
                                    model_name=model_name,
                                    profile=profile,
                                    prompt=prompt_for_log,
                                    raw_response=raw_response
                                )
                            
                            # 如果 box 没提取到东西，使用完整 content 进行裁判模型评测
                            answer_for_judge = original_response if not is_from_box else extracted_answer
                            
                            total_response_time += response_time
                            
                            # 使用裁判模型评判
                            is_correct, reasoning, judge_time, judge_response, judge_prompt = judge_answer(
                                model_answer=answer_for_judge,
                                gt_answer=round_answer,
                                question=round_question,
                                options=None
                            )
                            
                            # 详细日志：记录裁判模型响应
                            if LOG_MODE == "detailed" and DETAILED_LOG_FILE:
                                log_judge_response_detailed(
                                    question_id=item_id,
                                    round_key=round_key,
                                    model_name=model_name,
                                    profile=profile,
                                    model_answer=answer_for_judge,  # 使用实际用于评判的答案
                                    gt_answer=round_answer,
                                    is_match=is_correct,
                                    reasoning=reasoning,
                                    judge_time=judge_time,
                                    raw_response=judge_response,
                                    prompt=judge_prompt
                                )
                            
                            total_judge_time += judge_time
                            
                            if not is_correct:
                                all_rounds_correct = False
                            
                            logging.info(f"    轮次{round_num} 模型{model_name}: {'✓' if is_correct else '✗'}")
                            
                            # 保存该轮次的结果
                            # 注意：为了兼容 module2 格式，我们保存 model_answer 作为 process，extracted_answer 作为 answer
                            result_data = {
                                "model_name": model_name,
                                "prompt": prompt_for_log,  # 保存完整的对话历史（JSON格式）
                                "conversation_history": messages,  # 保存对话历史（列表格式）
                                "model_answer": model_answer,  # 完整回答（作为 process）
                                "extracted_answer": extracted_answer,  # 提取的答案（作为 answer）
                                "is_from_box": is_from_box,  # 是否从 box 中提取
                                "answer_for_judge": answer_for_judge,  # 实际用于评判的答案
                                "is_correct": is_correct,
                                "reasoning": reasoning,
                                "response_time": response_time,
                                "judge_time": judge_time,
                            }
                            # 只在详细模式下保存完整响应
                            if LOG_MODE == "detailed":
                                result_data["raw_response"] = raw_response
                                result_data["judge_response"] = judge_response
                            
                            rounds_data[round_key][model_name] = result_data
                            
                        except Exception as e:
                            logging.error(f"    轮次{round_num} 模型{model_name} 评测失败: {e}")
                            all_rounds_correct = False
                            if round_key not in rounds_data:
                                rounds_data[round_key] = {}
                            rounds_data[round_key][model_name] = {
                                "model_name": model_name,
                                "error": str(e),
                                "is_correct": False
                            }
                
                # 汇总每个模型的所有轮次结果
                for model_name in enabled_models:
                    model_rounds = []
                    model_all_correct = True
                    for round_key in round_keys:
                        if round_key in rounds_data and model_name in rounds_data[round_key]:
                            round_result = rounds_data[round_key][model_name]
                            model_rounds.append({
                                "round": round_key,
                                "question": question.get(round_key, ""),
                                "answer": answer.get(round_key, ""),
                                **round_result
                            })
                            if not round_result.get("is_correct", False):
                                model_all_correct = False
                    
                    profile_results["models"][model_name] = {
                        "model_name": model_name,
                        "is_multi_round": True,
                        "rounds": model_rounds,
                        "all_rounds_correct": model_all_correct,
                        "total_response_time": total_response_time,
                        "total_judge_time": total_judge_time,
                        "is_correct": model_all_correct  # 所有轮次都正确才算正确
                    }
            
            else:
                # 单轮问答：原有逻辑
                # 获取该用户画像的提示词（包含题型提示词）
                prompt = get_prompt(profile, question, options, normalized_question_type)
                logging.debug(f"提示词: {prompt[:200]}...")
                
            # 对每个启用的模型进行评测（并行）
            def eval_single_model(model_name: str):
                logging.info(f"  模型: {model_name}")
                try:
                    model_answer, response_time, raw_response = call_model_api(
                        model_name=model_name,
                        prompt=prompt,
                        image_paths=image_paths if image_paths else None
                    )
                    
                    if LOG_MODE == "detailed" and DETAILED_LOG_FILE:
                        log_model_response_detailed(
                            question_id=item_id,
                            model_name=model_name,
                            profile=profile,
                            prompt=prompt,
                            raw_response=raw_response
                        )
                    
                    extracted_answer, is_from_box, original_response = extract_answer_from_response(model_answer, has_options)
                    answer_for_judge = original_response if not is_from_box else extracted_answer
                    
                    logging.info(f"    模型回答: {extracted_answer[:100]}...")
                    if not is_from_box:
                        logging.info(f"    注意: 未从 \\boxed{{}} 中提取到答案，使用完整响应进行评测")
                    logging.info(f"    响应时间: {response_time:.2f}s")
                    
                    is_correct, reasoning, judge_time, judge_response, judge_prompt = judge_answer(
                        model_answer=answer_for_judge,
                        gt_answer=answer,
                        question=question,
                        options=options
                    )
                    
                    if LOG_MODE == "detailed" and DETAILED_LOG_FILE:
                        log_judge_response_detailed(
                            question_id=item_id,
                            model_name=model_name,
                            profile=profile,
                            model_answer=answer_for_judge,
                            gt_answer=answer,
                            is_match=is_correct,
                            reasoning=reasoning,
                            judge_time=judge_time,
                            raw_response=judge_response,
                            prompt=judge_prompt
                        )
                    
                    logging.info(f"    评判结果: {'✓' if is_correct else '✗'} ({reasoning[:50]}...)")
                    logging.info(f"    评判时间: {judge_time:.2f}s")
                    
                    result_data = {
                        "model_name": model_name,
                        "prompt": prompt,
                        "model_answer": model_answer,
                        "extracted_answer": extracted_answer,
                        "is_from_box": is_from_box,
                        "answer_for_judge": answer_for_judge,
                        "is_correct": is_correct,
                        "reasoning": reasoning,
                        "response_time": response_time,
                        "judge_time": judge_time,
                    }
                    if LOG_MODE == "detailed":
                        result_data["raw_response"] = raw_response
                        result_data["judge_response"] = judge_response
                    return model_name, result_data
                except Exception as e:
                    logging.error(f"    模型 {model_name} 评测失败: {e}")
                    return model_name, {
                        "model_name": model_name,
                        "error": str(e),
                        "is_correct": False
                    }

            with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
                futures = [executor.submit(eval_single_model, m) for m in enabled_models]
                for future in as_completed(futures):
                    model_name, model_result = future.result()
                    profile_results["models"][model_name] = model_result
            
            results["profiles"][profile] = profile_results
        
        return results
        
    except Exception as e:
        logging.error(f"数据项 {item_id} 评测失败: {e}")
        return {"question_id": item_id, "error": str(e)}


def calculate_statistics(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    计算统计信息
    
    Args:
        results: 评测结果列表
        
    Returns:
        统计信息字典
    """
    stats = {
        "total_items": len(results),
        "profiles": {},
        "models": {}
    }
    
    # 获取所有用户画像和模型
    all_profiles = set()
    all_models = set()
    
    for result in results:
        for profile in result.get("profiles", {}).keys():
            all_profiles.add(profile)
            for model_name in result["profiles"][profile].get("models", {}).keys():
                all_models.add(model_name)
    
    # 按用户画像统计
    for profile in all_profiles:
        profile_stats = {
            "total": 0,
            "correct": 0,
            "models": {}
        }
        
        for model_name in all_models:
            model_stats = {"total": 0, "correct": 0}
            
            for result in results:
                profile_data = result.get("profiles", {}).get(profile, {})
                model_data = profile_data.get("models", {}).get(model_name, {})
                
                # 支持多轮问答格式
                is_correct = None
                if "is_correct" in model_data:
                    is_correct = model_data["is_correct"]
                elif "all_rounds_correct" in model_data:
                    is_correct = model_data["all_rounds_correct"]
                
                if is_correct is not None:
                    model_stats["total"] += 1
                    if is_correct:
                        model_stats["correct"] += 1
                        profile_stats["correct"] += 1
                    profile_stats["total"] += 1
            
            model_stats["accuracy"] = model_stats["correct"] / model_stats["total"] if model_stats["total"] > 0 else 0
            profile_stats["models"][model_name] = model_stats
        
        profile_stats["accuracy"] = profile_stats["correct"] / profile_stats["total"] if profile_stats["total"] > 0 else 0
        stats["profiles"][profile] = profile_stats
    
    # 按模型统计（跨所有用户画像）
    for model_name in all_models:
        model_stats = {"total": 0, "correct": 0, "profiles": {}}
        
        for profile in all_profiles:
            profile_model_stats = {"total": 0, "correct": 0}
            
            for result in results:
                profile_data = result.get("profiles", {}).get(profile, {})
                model_data = profile_data.get("models", {}).get(model_name, {})
                
                # 支持多轮问答格式
                is_correct = None
                if "is_correct" in model_data:
                    is_correct = model_data["is_correct"]
                elif "all_rounds_correct" in model_data:
                    is_correct = model_data["all_rounds_correct"]
                
                if is_correct is not None:
                    profile_model_stats["total"] += 1
                    model_stats["total"] += 1
                    if is_correct:
                        profile_model_stats["correct"] += 1
                        model_stats["correct"] += 1
            
            profile_model_stats["accuracy"] = profile_model_stats["correct"] / profile_model_stats["total"] if profile_model_stats["total"] > 0 else 0
            model_stats["profiles"][profile] = profile_model_stats
        
        model_stats["accuracy"] = model_stats["correct"] / model_stats["total"] if model_stats["total"] > 0 else 0
        stats["models"][model_name] = model_stats
    
    # 按分类字段统计
    category_fields = ["question_type", "scenario", "capability", "difficulty", "source"]
    stats["by_category"] = {}
    
    for category_field in category_fields:
        category_stats = {}
        
        # 收集所有该字段的值
        category_values = set()
        for result in results:
            category_value = result.get(category_field)
            if category_value:
                category_values.add(category_value)
        
        # 对每个分类值进行统计
        for category_value in category_values:
            category_value_stats = {
                "total": 0,
                "correct": 0,
                "models": {}
            }
            
            for model_name in all_models:
                model_category_stats = {"total": 0, "correct": 0}
                
                for result in results:
                    if result.get(category_field) != category_value:
                        continue
                    
                    # 统计所有用户画像的结果
                    for profile in all_profiles:
                        profile_data = result.get("profiles", {}).get(profile, {})
                        model_data = profile_data.get("models", {}).get(model_name, {})
                        
                        # 支持多轮问答格式
                        is_correct = None
                        if "is_correct" in model_data:
                            is_correct = model_data["is_correct"]
                        elif "all_rounds_correct" in model_data:
                            is_correct = model_data["all_rounds_correct"]
                        
                        if is_correct is not None:
                            model_category_stats["total"] += 1
                            category_value_stats["total"] += 1
                            if is_correct:
                                model_category_stats["correct"] += 1
                                category_value_stats["correct"] += 1
                
                model_category_stats["accuracy"] = model_category_stats["correct"] / model_category_stats["total"] if model_category_stats["total"] > 0 else 0
                category_value_stats["models"][model_name] = model_category_stats
            
            category_value_stats["accuracy"] = category_value_stats["correct"] / category_value_stats["total"] if category_value_stats["total"] > 0 else 0
            category_stats[category_value] = category_value_stats
        
        if category_stats:
            stats["by_category"][category_field] = category_stats
    
    return stats


def calculate_output_statistics(results: List[Dict[str, Any]], enabled_models: List[str]) -> Dict[str, Any]:
    """
    基于最终输出格式计算统计信息（用于在输出文件中展示）
    
    Args:
        results: module2格式的结果列表（每个结果项可能包含多个模型字段）
        enabled_models: 启用的模型列表
        
    Returns:
        统计信息字典，包含总得分和按分类字段的得分
    """
    def _model_entry_is_valid(entry: Any) -> bool:
        """判定模型字段是否包含有效结果，过滤掉批量写入时生成的占位空结果。"""
        if not isinstance(entry, dict):
            return False
        if entry.get("response_time", 0) > 0:
            return True
        if entry.get("answer") not in ("", None, {}):
            return True
        if entry.get("process") not in ("", None, {}):
            return True
        return False
    
    model_keys = [f"model{i+1}" for i in range(len(enabled_models))]
    
    stats = {
        "total": {
            "total_count": 0,
            "correct_count": 0,
            "accuracy": 0.0
        },
        "by_model": {},
        "by_profile": {},
        "by_category": {}
    }
    
    # 统计总得分（逐模型而不是逐题），跳过占位空结果
    total_correct = 0
    total_count = 0
    for item in results:
        for idx, _ in enumerate(enabled_models):
            model_key = model_keys[idx]
            entry = item.get(model_key)
            if not _model_entry_is_valid(entry):
                continue
            total_count += 1
            if entry.get("match_gt", False):
                total_correct += 1
    
    stats["total"]["total_count"] = total_count
    stats["total"]["correct_count"] = total_correct
    stats["total"]["accuracy"] = total_correct / total_count if total_count > 0 else 0.0
    
    # 按模型统计
    for idx, model_name in enumerate(enabled_models):
        model_key = model_keys[idx]
        model_total = 0
        model_correct = 0
        
        for item in results:
            entry = item.get(model_key)
            if not _model_entry_is_valid(entry):
                continue
            model_total += 1
            if entry.get("match_gt", False):
                model_correct += 1
        
        stats["by_model"][model_name] = {
            "total_count": model_total,
            "correct_count": model_correct,
            "accuracy": model_correct / model_total if model_total > 0 else 0.0
        }
    
    # 按用户画像统计
    profiles = {item["profile"] for item in results if "profile" in item}
    
    for profile in profiles:
        profile_total = 0
        profile_correct = 0
        
        for item in results:
            if item.get("profile") != profile:
                continue
            for idx, _ in enumerate(enabled_models):
                model_key = model_keys[idx]
                entry = item.get(model_key)
                if not _model_entry_is_valid(entry):
                    continue
                profile_total += 1
                if entry.get("match_gt", False):
                    profile_correct += 1
        
        stats["by_profile"][profile] = {
            "total_count": profile_total,
            "correct_count": profile_correct,
            "accuracy": profile_correct / profile_total if profile_total > 0 else 0.0
        }
    
    # 按分类字段统计（只统计实际存在的字段）
    category_fields = ["question_type", "scenario", "capability", "difficulty", "source"]
    
    # 先检查哪些字段实际存在
    existing_fields = set()
    for item in results:
        for field in category_fields:
            if field in item and item[field]:
                existing_fields.add(field)
    
    # 只统计存在的字段
    for category_field in existing_fields:
        category_stats = {}
        
        # 收集所有该字段的值
        category_values = set()
        for item in results:
            category_value = item.get(category_field)
            if category_value:
                category_values.add(category_value)
        
        # 对每个分类值进行统计
        for category_value in category_values:
            category_total = 0
            category_correct = 0
            
            for item in results:
                if item.get(category_field) != category_value:
                    continue
                
                for idx, _ in enumerate(enabled_models):
                    model_key = model_keys[idx]
                    entry = item.get(model_key)
                    if not _model_entry_is_valid(entry):
                        continue
                    category_total += 1
                    if entry.get("match_gt", False):
                        category_correct += 1
            
            category_stats[category_value] = {
                "total_count": category_total,
                "correct_count": category_correct,
                "accuracy": category_correct / category_total if category_total > 0 else 0.0
            }
        
        if category_stats:
            stats["by_category"][category_field] = category_stats
    
    return stats


def main(args: argparse.Namespace):
    """主函数"""
    global DETAILED_LOG_FILE
    # 设置日志（从环境变量读取日志模式）
    log_mode = os.getenv("EVAL_LOG_MODE", "detailed")
    setup_logging(args.log_dir, args.log_level, log_mode)
    
    # 加载数据
    logging.info(f"加载数据: {args.input_file}")
    items = load_and_validate(args.input_file)
    logging.info(f"成功加载 {len(items)} 条数据")
    
    # 限制处理数量（如果设置了LIMIT环境变量）
    limit = os.getenv("EVAL_LIMIT", "")
    if limit and limit.isdigit():
        limit_num = int(limit)
        if limit_num > 0:
            # 是否随机选择
            use_random = os.getenv("EVAL_USE_RANDOM", "false").lower() in ("true", "1", "yes")
            if use_random:
                import random
                seed = os.getenv("EVAL_SEED", "")
                if seed and seed.isdigit():
                    random.seed(int(seed))
                random.shuffle(items)
            items = items[:limit_num]
            logging.info(f"限制处理数量: {limit_num} 条数据")
    
    # 确定要评测的模型和用户画像
    # 从环境变量读取要评测的模型列表（模型名称对应 MODEL_DEFINITIONS 中的 key）
    eval_model_names = get_eval_models()
    
    if not eval_model_names:
        raise ValueError(
            "没有指定要评测的模型。请在脚本中设置 EVAL_MODELS 环境变量，"
            "例如：export EVAL_MODELS='doubao,GLM,qwenvlmax'"
        )
    
    # 验证模型是否在 MODEL_DEFINITIONS 中
    enabled_models = []
    for model_name in eval_model_names:
        if model_name in MODEL_DEFINITIONS:
            enabled_models.append(model_name)
        else:
            logging.warning(f"模型 '{model_name}' 不在 MODEL_DEFINITIONS 中，已跳过")
    
    if not enabled_models:
        raise ValueError(f"没有有效的模型。请检查 EVAL_MODELS 环境变量和 MODEL_DEFINITIONS 配置")
    
    profiles = args.profiles if args.profiles else USER_PROFILES
    
    logging.info(f"启用的模型: {enabled_models}")
    logging.info(f"用户画像: {profiles}")
    
    # 检查：如果启用断点续传但没有指定输出文件名，报错
    use_custom_output_file = args.output_file is not None and args.output_file != ""
    if args.resume and not use_custom_output_file:
        error_msg = (
            "错误：启用断点续传时必须指定输出文件名（OUTPUT_FILE）。\n"
            "请在 run_eval.sh 中设置 OUTPUT_FILE，例如：OUTPUT_FILE=\"eval_results.json\""
        )
        logging.error(error_msg)
        raise ValueError(error_msg)
    
    # 输出目录固定为 ./outputs，按用户画像和模型分类组织
    base_output_dir = Path("./outputs")
    base_output_dir.mkdir(exist_ok=True)
    
    if use_custom_output_file:
        # 解析指定的输出文件名
        output_file_path = Path(args.output_file)
        # 只使用文件名部分，忽略路径（因为路径由 profile 和 model_name 决定）
        output_file_name = output_file_path.name
        base_name = output_file_path.stem
        file_ext = output_file_path.suffix.lstrip('.')
        
        # 如果文件有扩展名，使用扩展名；否则使用配置中的格式
        if file_ext:
            output_format = file_ext.lower()
        else:
            output_format = EVAL_CONFIG.get("output_format", "json").lower()
            file_ext = output_format
            output_file_name = f"{base_name}.{file_ext}"
        
        logging.info(f"使用指定的输出文件名: {output_file_name}")
        logging.info(f"输出格式: {output_format}")
        logging.info(f"文件将保存在: ./outputs/{{profile}}/{{model_name}}/{output_file_name}")
    else:
        # 使用自动生成的带时间戳的文件名（仅在不断点续传时）
        # 注意：如果启用断点续传，应该已经在上面的检查中报错了
        input_file_name = Path(args.input_file).stem  # 评测集命名（不含扩展名）
        limit_str = str(len(items)) if limit and limit.isdigit() and int(limit) > 0 else "all"
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_format = EVAL_CONFIG.get("output_format", "json").lower()
        output_file_name = f"eval_{input_file_name}_{limit_str}_{timestamp}.{output_format}"
        
        logging.info(f"使用自动生成的输出文件名: {output_file_name}")
        logging.info(f"输出格式: {output_format}")
        logging.info(f"文件将保存在: ./outputs/{{profile}}/{{model_name}}/{output_file_name}")
    
    # 辅助函数：获取下一个版本号的文件路径（类似 module1）
    def get_next_version_path(original_path: Path) -> Path:
        """如果文件已存在，生成_v2、_v3等版本号的文件路径"""
        if not original_path.exists():
            return original_path
        
        base_name = original_path.stem
        ext = original_path.suffix
        dir_path = original_path.parent
        
        counter = 2
        while True:
            new_name = f"{base_name}_v{counter}{ext}"
            new_path = dir_path / new_name
            if not new_path.exists():
                return new_path
            counter += 1
    
    # 为每个模型和用户画像组合创建输出文件
    output_files = {}  # {(model_name, profile): file_path}
    output_file_handles = {}  # {(model_name, profile): file_handle}  # 仅用于JSONL
    completed_items = {}  # {(model_name, profile): set(question_ids)}
    existing_results = {}  # {(model_name, profile): list(results)}
    
    for model_name in enabled_models:
        for profile in profiles:
            # 文件路径：./outputs/{profile}/{model_name}/{output_file_name}
            profile_model_dir = base_output_dir / profile / model_name
            profile_model_dir.mkdir(parents=True, exist_ok=True)
            
            # 断点续传：检查是否存在匹配的输出文件并读取已完成的问题
            existing_file = None
            if args.resume:
                # 断点续传模式下，必须指定了输出文件名（否则应该已经在上面的检查中报错）
                base_output_file = profile_model_dir / output_file_name
                if base_output_file.exists():
                    existing_file = base_output_file
                    output_file = base_output_file
                    logging.info(f"检测到输出文件: {base_output_file}")
                else:
                    # 检查是否有带版本号的文件（_v2, _v3等）
                    base_name_without_ext = Path(output_file_name).stem
                    pattern = f"{base_name_without_ext}_v*.{file_ext}"
                    versioned_files = list(profile_model_dir.glob(pattern))
                    if versioned_files:
                        # 使用最新的版本号文件
                        existing_file = max(versioned_files, key=lambda p: p.stat().st_mtime)
                        output_file = existing_file
                        logging.info(f"检测到带版本号的输出文件: {existing_file}")
                    else:
                        # 输出文件不存在，自动创建
                        output_file = base_output_file
                        logging.info(f"检测到输出文件不存在，将自动创建新文件: {output_file}")
            else:
                # 不续传
                if use_custom_output_file:
                    # 如果指定了输出文件名
                    base_output_file = profile_model_dir / output_file_name
                    if base_output_file.exists():
                        output_file = get_next_version_path(base_output_file)
                        logging.info(f"文件已存在，使用新版本: {output_file}")
                    else:
                        output_file = base_output_file
                else:
                    # 如果未指定输出文件名，生成新的带时间戳的文件名
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    output_file_name = f"eval_{input_file_name}_{limit_str}_{timestamp}.{output_format}"
                    output_file = profile_model_dir / output_file_name
            
            # 如果找到了已存在的文件，读取已完成的问题
            if existing_file and existing_file.exists():
                # 验证文件元数据（检查输入文件路径是否匹配）
                try:
                    if output_format == "jsonl":
                        # JSONL格式：读取第一行（统计信息）和已有结果
                        with open(existing_file, 'r', encoding='utf-8') as f:
                            first_line = f.readline().strip()
                            if first_line:
                                stats_data = json.loads(first_line)
                                # 检查输入文件路径（如果保存了的话）
                                # 这里可以扩展检查逻辑
                                pass
                            
                            # 读取已有结果
                            completed_ids = set()
                            results_list = []
                            for line in f:
                                line = line.strip()
                                if not line:
                                    continue
                                try:
                                    item = json.loads(line)
                                    item_id = item.get("question_id", "")
                                    if item_id:
                                        completed_ids.add(item_id)
                                        results_list.append(item)
                                except json.JSONDecodeError:
                                    continue
                            
                            completed_items[(model_name, profile)] = completed_ids
                            existing_results[(model_name, profile)] = results_list
                            output_file = existing_file
                            logging.info(f"  已加载 {len(completed_ids)} 个已完成的问题")
                    else:
                        # JSON格式：读取完整文件
                        with open(existing_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            if isinstance(data, dict) and "results" in data:
                                # 检查统计信息中的元数据
                                stats = data.get("statistics", {})
                                # 这里可以扩展检查逻辑
                                
                                # 读取已有结果
                                results_list = data.get("results", [])
                                completed_ids = set()
                                for item in results_list:
                                    item_id = item.get("question_id", "")
                                    if item_id:
                                        completed_ids.add(item_id)
                                
                                completed_items[(model_name, profile)] = completed_ids
                                existing_results[(model_name, profile)] = results_list
                                output_file = existing_file
                                logging.info(f"  已加载 {len(completed_ids)} 个已完成的问题")
                except Exception as e:
                    logging.warning(f"加载已有文件失败: {e}，将创建新文件")
                    # 如果加载失败，使用新文件路径（不覆盖 existing_file）
                    pass
            
            output_files[(model_name, profile)] = output_file
            
            # JSONL格式：打开文件句柄（追加模式）
            if output_format == "jsonl":
                file_handle = open(output_file, 'a', encoding='utf-8')
                output_file_handles[(model_name, profile)] = file_handle
                
                # 如果是新文件，写入统计信息占位符（第一行）
                if output_file.stat().st_size == 0:
                    stats_placeholder = {
                        "statistics": {
                            "total": {"total_count": 0, "correct_count": 0, "accuracy": 0.0},
                            "by_model": {},
                            "by_profile": {},
                            "by_category": {}
                        }
                    }
                    file_handle.write(json.dumps(stats_placeholder, ensure_ascii=False) + '\n')
                    file_handle.flush()
    
    # 初始化批量写入buffer（仅用于JSON格式）
    batch_size = EVAL_CONFIG.get("batch_size", 10)  # 默认每10条保存一次
    result_buffers = {}  # {(model_name, profile): list(results)}
    for model_name in enabled_models:
        for profile in profiles:
            result_buffers[(model_name, profile)] = existing_results.get((model_name, profile), [])
    
    # 辅助函数：将结果转换为module2格式并写入
    def convert_and_save_result(result: Dict[str, Any], model_name: str, profile: str):
        """将单个评测结果转换为module2格式并保存"""
        profile_data = result.get("profiles", {}).get(profile, {})
        model_data = profile_data.get("models", {}).get(model_name, {})
        
        if not model_data:
            return None
        
        # 确定模型键
        model_key = None
        for idx, enabled_model in enumerate(enabled_models, 1):
            if enabled_model == model_name:
                model_key = f"model{idx}"
                break
        if not model_key:
            model_key = "model1"
        
        # 获取模型答案和推理过程
        model_answer = model_data.get("model_answer", "")
        extracted_answer = model_data.get("extracted_answer", "")
        is_multi_round = result.get("is_multi_round", False)
        
        # 处理多轮问答
        if is_multi_round and isinstance(model_data.get("rounds"), list):
            answer_dict = {}
            process_dict = {}
            for round_data in model_data.get("rounds", []):
                round_key = round_data.get("round", "")
                if round_key:
                    answer_dict[round_key] = round_data.get("extracted_answer", "")
                    process_dict[round_key] = round_data.get("model_answer", "")
            model_answer_value = answer_dict if answer_dict else {}
            process_value = process_dict if process_dict else {}
        else:
            model_answer_value = extracted_answer if extracted_answer else ""
            process_value = model_answer if model_answer else ""
        
        is_correct = model_data.get("is_correct", False) or model_data.get("all_rounds_correct", False)
        
        # 构建module2格式的结果项
        module2_item = {
            "question_id": result.get("question_id", result.get("id", "")),
            "question": result.get("question", ""),
            "answer": result.get("answer", ""),
            "question_type": result.get("question_type", ""),
            "image_type": result.get("image_type", ""),
            "image_path": result.get("image_path", ""),
            "options": result.get("options"),
            "profile": profile,
        }
        
        # 保留分类字段
        for field in ["scenario", "capability", "difficulty", "source"]:
            if field in result:
                module2_item[field] = result[field]
        
        # 添加模型结果
        module2_item[model_key] = {
            "process": process_value,
            "answer": model_answer_value,
            "model_name": model_name,
            "response_time": model_data.get("response_time", 0.0),
            "match_gt": is_correct
        }
        
        # 添加其他模型字段
        for idx, other_model in enumerate(enabled_models, 1):
            other_model_key = f"model{idx}"
            if other_model_key != model_key:
                module2_item[other_model_key] = {
                    "process": "" if not is_multi_round else {},
                    "answer": "" if not is_multi_round else {},
                    "model_name": other_model,
                    "response_time": 0.0,
                    "match_gt": False
                }
        
        # 添加comparison字段
        module2_item["comparison"] = {
            "agreement_with_gt": 1 if is_correct else 0
        }
        
        return module2_item
    
    # 辅助函数：批量写入JSON格式结果
    def flush_buffer(model_name: str, profile: str):
        """刷新指定模型和用户画像的buffer"""
        key = (model_name, profile)
        if key not in result_buffers:
            return
        
        buffer = result_buffers[key]
        if not buffer:
            return
        
        output_file = output_files[key]
        
        try:
            # 读取现有数据
            existing_data = {"statistics": {}, "results": []}
            if output_file.exists() and output_file.stat().st_size > 0:
                with open(output_file, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
            
            # 合并结果（去重）
            existing_ids = {item.get("question_id", "") for item in existing_data.get("results", [])}
            new_results = []
            for item in buffer:
                item_id = item.get("question_id", "")
                if item_id and item_id not in existing_ids:
                    new_results.append(item)
                    existing_ids.add(item_id)
            
            if new_results:
                existing_data["results"].extend(new_results)
                
                # 重新计算统计信息
                stats = calculate_output_statistics(existing_data["results"], enabled_models)
                existing_data["statistics"] = stats
                
                # 保存
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(existing_data, f, ensure_ascii=False, indent=2)
                
                logging.debug(f"批量保存 {len(new_results)} 条结果到 {output_file.name}")
            
            # 清空buffer（只保留已保存的结果用于去重检查）
            result_buffers[key] = existing_data["results"]
        except Exception as e:
            logging.error(f"批量保存失败 ({model_name}, {profile}): {e}")
    
    # 并发配置
    workers = os.getenv("EVAL_WORKERS", "")
    try:
        workers = int(workers) if str(workers).strip() else 1
    except ValueError:
        workers = 1
    if workers <= 0:
        workers = 1
    separator = "=" * 40
    combos = [(m, p) for m in enabled_models for p in profiles]
    combo_workers = max(1, min(len(combos), workers))
    per_combo_workers = max(1, workers // combo_workers)
    logging.info(
        f"并发配置: total_workers={workers}, combo_workers={combo_workers}, per_combo_workers={per_combo_workers}"
    )

    # 评测每个模型/用户画像组合，并行调度组合，在组合内部再并发题目（多轮视为单任务）
    failures = []  # 收集失败问题

    def process_combo(model_name: str, profile: str):
        key = (model_name, profile)
        logging.info(f"\n{separator}\n开始模型: {model_name} | 画像: {profile}\n{separator}")
        futures = {}
        try:
            with ThreadPoolExecutor(max_workers=per_combo_workers) as executor:
                for item in items:
                    item_id = item.get("question_id") or item.get("id", "")
                    if item_id and item_id in completed_items.get(key, set()):
                        continue
                    future = executor.submit(
                        evaluate_single_item,
                        item,
                        [model_name],  # 单模型，避免内部再次并行
                        [profile],
                        1             # 内部不开线程池
                    )
                    futures[future] = item_id
                
                # 为每个模型/画像组合单独显示一个进度条，前缀包含模型名和画像，便于区分
                for future in tqdm(
                    as_completed(futures),
                    total=len(futures),
                    desc=f"{model_name}-{profile}",
                ):
                    item_id = futures[future]
                    try:
                        result = future.result()
                    except Exception as e:
                        failures.append({"question_id": item_id, "reason": f"future exception: {e}"})
                        continue
                    
                    if not result:
                        failures.append({"question_id": item_id, "reason": "evaluate_single_item returned None"})
                        continue
                    if isinstance(result, dict) and "error" in result:
                        failures.append({"question_id": result.get("question_id", item_id), "reason": result.get("error", "unknown error")})
                        continue
                    
                    module2_item = convert_and_save_result(result, model_name, profile)
                    if not module2_item:
                        continue
                    
                    item_id = module2_item.get("question_id", "") or item_id
                    if not item_id:
                        continue
                    if item_id in completed_items.get(key, set()):
                        continue
                    
                    if key not in completed_items:
                        completed_items[key] = set()
                    completed_items[key].add(item_id)
                    
                    if output_format == "jsonl":
                        file_handle = output_file_handles.get(key)
                        if file_handle:
                            try:
                                file_handle.write(json.dumps(module2_item, ensure_ascii=False) + '\n')
                                file_handle.flush()
                            except Exception as e:
                                logging.error(f"实时写入失败 ({model_name}, {profile}): {e}")
                    else:
                        if key not in result_buffers:
                            result_buffers[key] = []
                        result_buffers[key].append(module2_item)
                        
                        if len(result_buffers[key]) >= batch_size:
                            flush_buffer(model_name, profile)
        finally:
            # 确保当前模型画像的缓冲被刷新（即使异常/中断）
            if output_format == "json":
                flush_buffer(model_name, profile)

    interrupted = False
    try:
        with ThreadPoolExecutor(max_workers=combo_workers) as combo_executor:
            combo_future_map = {combo_executor.submit(process_combo, m, p): (m, p) for m, p in combos}
            for future in as_completed(combo_future_map):
                m, p = combo_future_map[future]
                try:
                    future.result()
                except Exception as e:
                    failures.append({"question_id": "", "reason": f"combo {m}-{p} exception: {e}"})
    except KeyboardInterrupt:
        interrupted = True
        logging.warning("检测到中断信号，正在尝试优雅停止并刷盘...")
        try:
            combo_executor.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass

    # 关闭所有文件句柄（JSONL格式，在更新统计信息前关闭）
    if output_format == "jsonl":
        for key, file_handle in output_file_handles.items():
            try:
                file_handle.close()
            except Exception as e:
                logging.warning(f"关闭文件句柄失败 {key}: {e}")
    
    # 刷新所有buffer（JSON格式）
    if output_format == "json":
        logging.info("\n刷新所有buffer...")
        for model_name in enabled_models:
            for profile in profiles:
                flush_buffer(model_name, profile)
    
    # 更新统计信息并保存最终结果
    logging.info("\n更新统计信息...")
    for model_name in enabled_models:
        for profile in profiles:
            key = (model_name, profile)
            output_file = output_files[key]
            
            try:
                if output_format == "jsonl":
                    # JSONL格式：读取所有结果，重新计算统计信息，更新第一行
                    all_results = []
                    with open(output_file, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                        if lines:
                            # 跳过第一行（统计信息）
                            for line in lines[1:]:
                                line = line.strip()
                                if line:
                                    try:
                                        all_results.append(json.loads(line))
                                    except json.JSONDecodeError:
                                        continue
                    
                    # 重新计算统计信息
                    stats = calculate_output_statistics(all_results, enabled_models)
                    
                    # 重写文件（更新第一行统计信息）
                    with open(output_file, 'w', encoding='utf-8') as f:
                        f.write(json.dumps({"statistics": stats}, ensure_ascii=False) + '\n')
                        for item in all_results:
                            f.write(json.dumps(item, ensure_ascii=False) + '\n')
                    
                    logging.info(f"已更新统计信息: {output_file.name} (共 {len(all_results)} 条结果)")
                else:
                    # JSON格式：重新计算统计信息
                    with open(output_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    all_results = data.get("results", [])
                    stats = calculate_output_statistics(all_results, enabled_models)
                    data["statistics"] = stats
                    
                    with open(output_file, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    
                    logging.info(f"已更新统计信息: {output_file.name} (共 {len(all_results)} 条结果)")
            except Exception as e:
                logging.error(f"更新统计信息失败 ({model_name}, {profile}): {e}")
    
    # 如果是中断退出，保存完就立刻静默退出（不再打印后续摘要日志）
    if interrupted:
        logging.info(f"\n评测中断，但已保存当前结果并更新统计，共生成 {len(output_files)} 个输出文件，准备静默退出。")
        # 直接退出进程，避免线程池清理阶段产生多余日志
        os._exit(0)
    
    logging.info(f"\n评测完成！共生成 {len(output_files)} 个输出文件")
    
    # 失败摘要
    logging.info("\n" + "="*60)
    logging.info("失败摘要")
    logging.info("="*60)
    if not failures:
        logging.info("所有问题均处理成功，未记录失败。")
    else:
        logging.info(f"失败总数: {len(failures)}")
        for fail in failures:
            logging.info(f"- question_id: {fail.get('question_id','')} | reason: {fail.get('reason','')}")
    # 详细日志文件也写入失败摘要
    if DETAILED_LOG_FILE:
        with log_lock:
            try:
                DETAILED_LOG_FILE.write("=" * 80 + "\n")
                DETAILED_LOG_FILE.write("失败摘要\n")
                DETAILED_LOG_FILE.write("=" * 80 + "\n")
                if not failures:
                    DETAILED_LOG_FILE.write("所有问题均处理成功，未记录失败。\n")
                else:
                    DETAILED_LOG_FILE.write(f"失败总数: {len(failures)}\n")
                    for fail in failures:
                        DETAILED_LOG_FILE.write(f"- question_id: {fail.get('question_id','')} | reason: {fail.get('reason','')}\n")
                DETAILED_LOG_FILE.write("\n")
                DETAILED_LOG_FILE.flush()
            except Exception as e:
                logging.warning(f"写入失败摘要到详细日志失败: {e}")
    
    # 打印统计摘要（从输出文件中读取）
    logging.info("\n" + "="*60)
    logging.info("统计摘要")
    logging.info("="*60)
    
    for model_name in enabled_models:
        for profile in profiles:
            key = (model_name, profile)
            output_file = output_files[key]
            
            try:
                if output_file.exists():
                    if output_format == "jsonl":
                        with open(output_file, 'r', encoding='utf-8') as f:
                            first_line = f.readline().strip()
                            if first_line:
                                stats_data = json.loads(first_line)
                                stats = stats_data.get("statistics", {})
                    else:
                        with open(output_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            stats = data.get("statistics", {})
                    
                    total_stats = stats.get("total", {})
                    logging.info(f"\n{model_name} - {profile}:")
                    logging.info(f"  总准确率: {total_stats.get('accuracy', 0):.2%} ({total_stats.get('correct_count', 0)}/{total_stats.get('total_count', 0)})")
            except Exception as e:
                logging.warning(f"读取统计信息失败 ({model_name}, {profile}): {e}")
    
    
    # 关闭详细日志文件
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


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='金融领域多用户画像评测脚本')
    parser.add_argument('--input_file', type=str, required=True, help='输入文件路径（JSON或JSONL）')
    parser.add_argument('--output_file', type=str, default=None, 
                       help='输出文件名（可选，支持 .json 或 .jsonl）。文件将保存在 ./outputs/{profile}/{model_name}/ 目录下')
    parser.add_argument('--log_dir', type=str, default='logs', help='日志目录')
    parser.add_argument('--log_level', type=str, default='INFO', help='日志级别')
    parser.add_argument('--profiles', type=str, nargs='+', default=None, 
                       help='用户画像列表（beginner/retail/expert/expert_cot），默认全部')
    parser.add_argument('--resume', action='store_true', help='是否启用断点续跑（从输出文件中读取已处理的问题）')
    
    args = parser.parse_args()
    main(args)
