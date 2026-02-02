"""
结果转换和保存模块
负责将评测结果转换为module2格式并保存到文件
"""
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from .result_utils import build_process_value
from .statistics import calculate_output_statistics


def convert_to_module2_format(
    result: Dict[str, Any],
    model_name: str,
    profile: str
) -> Optional[Dict[str, Any]]:
    """
    将单个评测结果转换为module2格式
    
    Args:
        result: 评测结果字典
        model_name: 模型名称
        profile: 用户画像
        
    Returns:
        module2格式的结果项，如果转换失败返回None
    """
    profile_data = result.get("profiles", {}).get(profile, {})
    model_data = profile_data.get("models", {}).get(model_name, {})
    
    if not model_data:
        return None
    
    # 统一使用"model"作为模型键（因为一个文件只有一个模型的输出）
    model_key = "model"
    
    # 获取模型答案和推理过程（单轮题目使用）
    model_answer = model_data.get("model_answer", "")
    extracted_answer = model_data.get("extracted_answer", "")
    is_multi_round = result.get("is_multi_round", False)
    
    # 处理多轮问答
    rounds_list = model_data.get("rounds", [])
    
    # 调试：检查数据传递
    if is_multi_round:
        logging.info(f"🔍 convert_to_module2_format: question_id={result.get('question_id', '')}, is_multi_round={is_multi_round}")
        logging.info(f"🔍 model_data.keys()={list(model_data.keys())}, has_rounds={'rounds' in model_data}")
        logging.info(f"🔍 rounds_list类型={type(rounds_list)}, rounds_list长度={len(rounds_list) if isinstance(rounds_list, list) else 0}")
        if isinstance(rounds_list, list) and len(rounds_list) > 0:
            logging.info(f"🔍 rounds_list前2项: {[r.get('round', 'NO_ROUND') for r in rounds_list[:2]]}")
        elif 'rounds' in model_data:
            logging.warning(f"⚠️ rounds字段存在但值为: {type(model_data['rounds'])}, 内容: {str(model_data['rounds'])[:200]}")
    
    if is_multi_round and isinstance(rounds_list, list) and len(rounds_list) > 0:
        # 多轮题目：按 round 分开保存
        answer_dict = {}
        process_dict = {}
        match_gt_dict = {}  # 多轮题目：按轮次记录正确性
        judge_reasoning_dict = {}  # 多轮题目：按轮次记录裁判推理
        
        for round_data in rounds_list:
            round_key = round_data.get("round", "")
            if not round_key:
                # 尝试从其他字段获取 round_key
                if "question" in round_data:
                    # 尝试从 question 字段推断（如果 question 是字典，取第一个 key）
                    q = round_data.get("question", "")
                    if isinstance(q, dict):
                        round_key = list(q.keys())[0] if q else ""
                    elif isinstance(q, str) and "round" in str(round_data):
                        # 尝试从其他字段推断
                        for key in round_data.keys():
                            if "round" in str(key).lower():
                                round_key = str(key)
                                break
            
            if round_key:
                # 如果存在error字段，确保answer相关字段都为空，不传入错误信息
                if "error" in round_data:
                    round_answer = ""
                    round_process = ""
                    round_correct = False
                    round_reasoning = ""
                else:
                    # 提取每轮的答案和过程
                    round_answer = round_data.get("extracted_answer", "")
                    # 使用思考内容 + 去掉 boxed 的正文 作为 process
                    raw_round_answer = round_data.get("model_answer", "") or round_data.get("process", "")
                    round_process = build_process_value(raw_round_answer, round_data)
                    round_correct = round_data.get("is_correct", False)
                    round_reasoning = round_data.get("reasoning", "")  # 提取裁判推理
                    
                    # 如果 extracted_answer 为空，尝试从其他字段获取
                    if not round_answer:
                        round_answer = round_data.get("answer", "")
                
                answer_dict[round_key] = round_answer
                process_dict[round_key] = round_process
                match_gt_dict[round_key] = round_correct
                judge_reasoning_dict[round_key] = round_reasoning
                logging.info(f"✅ 提取轮次 {round_key}: answer长度={len(round_answer) if round_answer else 0}, process长度={len(round_process) if round_process else 0}, correct={round_correct}")
            else:
                logging.warning(f"⚠️ 轮次数据缺少 round 字段: {list(round_data.keys())}")
        
        # 确保字典不为空
        if answer_dict and len(answer_dict) > 0:
            model_answer_value = answer_dict
            process_value = process_dict
            match_gt_value = match_gt_dict
            judge_reasoning_value = judge_reasoning_dict
            logging.info(f"✅ 多轮题目 {result.get('question_id', '')} 成功转换为字典格式: {list(answer_dict.keys())}, 共 {len(answer_dict)} 轮")
        else:
            # 如果提取失败，降级为单轮格式
            logging.error(f"❌ 多轮题目 {result.get('question_id', '')} 的 rounds 数据提取失败！rounds_list长度={len(rounds_list) if isinstance(rounds_list, list) else 0}, answer_dict长度={len(answer_dict)}")
            logging.error(f"    rounds_list内容: {rounds_list}")
            # 尝试从最后一轮获取数据（降级处理）
            if isinstance(rounds_list, list) and len(rounds_list) > 0:
                last_round = rounds_list[-1]
                fallback_answer = last_round.get("extracted_answer", "") or last_round.get("answer", "")
                fallback_process = last_round.get("model_answer", "") or last_round.get("process", "")
                fallback_reasoning = last_round.get("reasoning", "")
                logging.warning(f"   降级：使用最后一轮数据作为单轮格式")
                model_answer_value = fallback_answer
                process_value = fallback_process
                match_gt_value = last_round.get("is_correct", False)
                judge_reasoning_value = fallback_reasoning
            else:
                # 完全降级为单轮格式
                model_answer_value = extracted_answer if extracted_answer else ""
                process_value = build_process_value(model_answer, model_data)
                match_gt_value = model_data.get("is_correct", False) or model_data.get("all_rounds_correct", False)
                judge_reasoning_value = model_data.get("reasoning", "")
    else:
        # 单轮题目：答案仍然是提取后的 answer，process 使用思考内容 + 去掉 boxed 的正文
        # 如果存在error字段，确保answer相关字段都为空，不传入错误信息
        if "error" in model_data:
            model_answer_value = ""
            process_value = ""
            match_gt_value = False
            judge_reasoning_value = ""
        else:
            model_answer_value = extracted_answer if extracted_answer else ""
            process_value = build_process_value(model_answer, model_data)
            match_gt_value = model_data.get("is_correct", False) or model_data.get("all_rounds_correct", False)
            judge_reasoning_value = model_data.get("reasoning", "")
    
    # 构建module2格式的结果项
    # 处理 image_path：确保始终为数组格式
    image_paths_result = result.get("image_paths", [])
    if not image_paths_result:
        # 如果没有 image_paths，尝试从 image_path 获取（可能是字符串或数组）
        image_path_raw = result.get("image_path", "")
        if isinstance(image_path_raw, list):
            image_paths_result = image_path_raw
        elif image_path_raw:
            image_paths_result = [image_path_raw]
        else:
            image_paths_result = []
    
    module2_item = {
        "question_id": result.get("question_id", result.get("id", "")),
        "question": result.get("question", ""),
        "answer": result.get("answer", ""),
        "question_type": result.get("question_type", ""),
        "image_type": result.get("image_type", ""),
        "image_path": image_paths_result,  # 使用数组格式保存所有图片路径
        "options": result.get("options"),
        "profile": profile,
    }
    
    # 保留分类字段
    for field in ["scenario", "capability", "difficulty", "source", "language", "fintype"]:
        if field in result:
            module2_item[field] = result[field]
    
    # 保留 original_image_path 字段（确保为数组格式）
    original_image_path_result = result.get("original_image_path", [])
    if original_image_path_result:
        # 如果已经是数组，直接使用；如果是字符串，转换为数组
        if isinstance(original_image_path_result, list):
            module2_item["original_image_path"] = original_image_path_result
        elif isinstance(original_image_path_result, str):
            module2_item["original_image_path"] = [original_image_path_result] if original_image_path_result else []
    
    # 获取响应时间（多轮题目使用 total_response_time，单轮题目使用 response_time）
    if is_multi_round and "total_response_time" in model_data:
        response_time_value = model_data.get("total_response_time", 0.0)
    else:
        response_time_value = model_data.get("response_time", 0.0)
    
    # 添加模型结果（只保存当前模型的数据，不保存其他模型的数据）
    module2_item[model_key] = {
        "process": process_value,
        "answer": model_answer_value,
        "model_name": model_name,
        "response_time": response_time_value,
        "match_gt": match_gt_value,  # 多轮题目为字典格式 {round1: true/false, round2: true/false}，单轮题目为布尔值
        "judge_reasoning": judge_reasoning_value  # 裁判模型的推理：多轮题目为字典格式 {round1: "...", round2: "..."}，单轮题目为字符串
    }
    
    # 如果是多轮题目，保存每轮的正确性信息（用于按轮次统计，不影响输出格式）
    if is_multi_round and isinstance(model_data.get("rounds"), list):
        rounds_info = []
        for round_data in model_data.get("rounds", []):
            rounds_info.append({
                "round": round_data.get("round", ""),
                "is_correct": round_data.get("is_correct", False)
            })
        module2_item["_rounds_info"] = rounds_info  # 隐藏字段，用于统计
    
    # 添加comparison字段
    # 对于多轮题目，检查所有轮次是否都正确；对于单轮题目，直接使用 is_correct
    if is_multi_round and isinstance(match_gt_value, dict):
        # 多轮题目：所有轮次都正确才算正确
        all_rounds_correct = all(match_gt_value.values()) if match_gt_value else False
        agreement_value = 1 if all_rounds_correct else 0
    else:
        # 单轮题目：直接使用布尔值
        agreement_value = 1 if match_gt_value else 0
    
    module2_item["comparison"] = {
        "agreement_with_gt": agreement_value
    }
    
    return module2_item


def flush_json_buffer(
    model_name: str,
    profile: str,
    result_buffers: Dict,
    output_files: Dict,
    enabled_models: List[str]
):
    """
    刷新指定模型和用户画像的JSON格式buffer
    
    Args:
        model_name: 模型名称
        profile: 用户画像
        result_buffers: 结果缓冲区字典 {(model_name, profile): list(results)}
        output_files: 输出文件字典 {(model_name, profile): file_path}
        enabled_models: 启用的模型列表
    """
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
        
        # 保存策略：保留所有记录（包括重复的），直接追加新结果
        # 去重逻辑只在续传判断和算分时使用，保存时不做去重
        existing_results = existing_data.get("results", [])
        
        # 直接追加新结果，不做去重（和JSONL格式保持一致）
        new_results = []
        for item in buffer:
            new_results.append(item)
        
        # 合并所有结果（保留所有记录，包括重复的）
        final_results = existing_results + new_results
        
        if new_results:
            # 如果有新结果，需要保存
            existing_data["results"] = final_results
            
            # 重新计算统计信息（统计时会自动去重）
            stats = calculate_output_statistics(final_results, enabled_models)
            existing_data["statistics"] = stats
            
            # 原子写入：先写入临时文件，成功后再替换原文件（避免数据丢失）
            temp_file = output_file.with_suffix(output_file.suffix + '.tmp')
            try:
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(existing_data, f, ensure_ascii=False, indent=2)
                # 写入成功后再替换原文件（原子操作）
                temp_file.replace(output_file)
                logging.debug(f"批量保存 {len(new_results)} 条新结果到 {output_file.name} (共 {len(final_results)} 条结果，保留所有记录)")
                
                # 写入成功后才清空buffer（已保存的结果已写入文件）
                # 注意：不应该把final_results放回buffer，否则会导致结果重复累积
                result_buffers[key] = []
            except Exception as e:
                logging.error(f"  ❌ 写入临时文件失败: {e}，保留原文件不变，buffer保持不变")
                if temp_file.exists():
                    temp_file.unlink()  # 清理临时文件
                raise
    except Exception as e:
        logging.error(f"批量保存失败 ({model_name}, {profile}): {e}")

