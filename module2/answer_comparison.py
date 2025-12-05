"""
答案对比模块
对比三个模型的答案
使用规范的OpenAI格式调用模型，支持自定义模型名称
支持并行调用三个模型以提高速度
"""
import os
import sys
import time
import json
import re
from typing import List, Dict, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from module2.config import MODEL_CONFIG
from utils import count_agreement
from models.model1 import call_model1_api
from models.model2 import call_model2_api
from models.model3 import call_model3_api
from module2.logger import log_model_response, log_question_start


class AnswerComparison:
    """答案对比器"""
    
    def __init__(self, debug_mode: bool = False):
        self.model1_config = MODEL_CONFIG["model1"]
        self.model2_config = MODEL_CONFIG["model2"]
        self.model3_config = MODEL_CONFIG["model3"]
        self.model1_enabled = self.model1_config.get("enabled", True)
        self.model2_enabled = self.model2_config.get("enabled", True)
        self.model3_enabled = self.model3_config.get("enabled", True)
        self.question_count = 0  # 用于跟踪问题数量，判断是否是第一个问题
        self.debug_mode = debug_mode
        self.current_question_id = "unknown"  # 当前正在处理的问题ID
        
        # 使用MODEL_CONFIG中的自定义模型名称（api_config_name）
        # 必须从MODEL_CONFIG中获取，不能有默认值
        self.model1_api_config_name = self.model1_config.get("name")
        self.model2_api_config_name = self.model2_config.get("name")
        self.model3_api_config_name = self.model3_config.get("name")
        
        if not self.model1_api_config_name:
            raise ValueError("MODEL_CONFIG['model1']['name'] 必须配置，指向 API_CONFIG 中的某个 key")
        if not self.model2_api_config_name:
            raise ValueError("MODEL_CONFIG['model2']['name'] 必须配置，指向 API_CONFIG 中的某个 key")
        if not self.model3_api_config_name:
            raise ValueError("MODEL_CONFIG['model3']['name'] 必须配置，指向 API_CONFIG 中的某个 key")
    
    def get_model_answer(self, model_num: int, api_config_name: str, enabled: bool, 
                         question: str, image_path: str = "") -> Tuple[str, str, float, Optional[dict], str]:
        """
        获取模型答案（直接调用模型API函数）
        
        ⚠️ 提示词拼接说明：
        - question 参数：
          * 单轮题：来自 model_evaluation.py::_build_model_question() 构建的完整问题文本
          * 多轮题：来自 get_model_answer_multi_round() 构造的 round_question
        - 在 call_model*_api() 中，使用 PROMPT_TEMPLATE.format(question=question) 拼接
        - 最终提示词 = PROMPT_TEMPLATE + question
        - 详见 module2/PROMPT_FLOW.md
        
        Args:
            model_num: 模型编号（1, 2, 或 3）
            api_config_name: API配置名称（用于日志）
            enabled: 是否启用
            question: 问题文本（已包含格式要求）
            image_path: 图片路径
        
        Returns:
            (answer, process, response_time, raw_response_json, final_prompt): 
            - answer: 从 \boxed{} 中提取的答案
            - process: 推理过程（去除 \boxed{} 后的文本）
            - response_time: 响应时间（秒）
            - raw_response_json: 原始API响应（字典格式）
            - final_prompt: 最终提交给模型的完整提示词（用于日志记录）
        """
        if not enabled:
            print(f"    模型{model_num} ({api_config_name}) 已禁用，跳过")
            return "", "", 0.0, None, ""
        
        # 验证输入
        if not question or not question.strip():
            print(f"      ⚠️ 警告：模型{model_num} 的问题为空，跳过调用")
            return "", "", 0.0, None, ""
        
        try:
            print(f"      调用模型{model_num} API: {api_config_name}, 问题长度: {len(question)}, 图片: {image_path if image_path else '无'}")
            
            # 直接调用对应的模型API函数
            if model_num == 1:
                result = call_model1_api(question, image_path if image_path else None)
            elif model_num == 2:
                result = call_model2_api(question, image_path if image_path else None)
            elif model_num == 3:
                result = call_model3_api(question, image_path if image_path else None)
            else:
                raise ValueError(f"未知的模型编号: {model_num}，只支持 1, 2, 3")
            
            # result格式: [process, answer, response_time, raw_response_json, final_prompt]
            # 需要验证返回格式
            if not isinstance(result, (list, tuple)) or len(result) < 2:
                print(f"      ⚠️ 警告：模型{model_num} 返回格式异常: {result}")
                return "", "", 0.0, None, question
            
            # 根据实际返回格式解析（格式为 [process, answer, response_time, raw_response_json, final_prompt]）
            process = str(result[0]) if len(result) > 0 and result[0] else ""
            answer = str(result[1]) if len(result) > 1 and result[1] else ""
            response_time = float(result[2]) if len(result) > 2 and result[2] else 0.0
            raw_response_json = result[3] if len(result) > 3 else None
            final_prompt = result[4] if len(result) > 4 else question  # 完整的最终提示词，用于日志
            
            # 验证结果
            if not answer:
                print(f"      ⚠️ 警告：模型{model_num} 返回的答案为空")
            
            print(f"      模型{model_num} API调用完成，耗时: {response_time:.2f}秒")
            print(f"      解析结果: answer长度={len(answer)}, process长度={len(process)}")
            
            return answer, process, response_time, raw_response_json, final_prompt
        except Exception as e:
            import traceback
            print(f"      ❌ 获取模型{model_num} ({api_config_name}) 答案时出错: {e}")
            if self.debug_mode:
                print(f"      错误详情:")
                traceback.print_exc()
            return "", "", 0.0, None, question
    
    def get_model_answer_multi_round(
        self,
        model_num: int,
        api_config_name: str,
        enabled: bool,
        question_rounds: Dict[str, str],
        image_path: str = "",
        question_id: str = "unknown",
        question_num: int = 0,
        format_requirements: str = "",  # 已废弃，保留以兼容接口
    ) -> Tuple[Dict[str, str], Dict[str, str], float, Optional[dict], str]:
        """
        针对多轮对话题型，按轮依次提问，同一个模型多次调用：
        - question_rounds: {"round1": "......", "round2": "...", ...}
        - format_requirements: 格式要求文本（从 _build_model_question 中提取的多轮题格式要求）
        
        ⚠️ 提示词拼接流程：
        1. 第一轮：round_question = "round1：{问题文本}"
        2. 后续轮：round_question = "历史对话\n\n现在是新的轮次 roundX，请只回答本轮问题：{问题文本}"
        3. round_question 传给 get_model_answer -> call_model*_api
        4. call_model*_api 使用 PROMPT_TEMPLATE.format(question=round_question) 拼接
        5. 最终提示词 = PROMPT_TEMPLATE + round_question（格式要求已在 PROMPT_TEMPLATE 中统一说明）
        
        返回值：
        - final_answer: 字典格式，例如 {"round1": "答案1", "round2": "答案2"}，每个 round 都是独立的
        - final_process: 字典格式，例如 {"round1": "推理过程1", "round2": "推理过程2"}，每个 round 都是独立的
        - total_time: 所有轮次耗时之和
        - last_raw_json: 最后一轮的原始响应JSON
        - last_final_prompt: 最后一轮的完整提示词（用于日志）
        """
        if not enabled:
            print(f"    模型{model_num} ({api_config_name}) 已禁用（多轮），跳过")
            return "", "", 0.0, None, ""

        answers: Dict[str, str] = {}
        processes: Dict[str, str] = {}
        total_time = 0.0
        last_raw_json: Optional[dict] = None
        last_final_prompt: str = ""  # 最后一轮的完整提示词
        # 带上下文的对话历史（按模型自己的回答累积）
        history_segments = []
        
        def _round_sort_key(k: str) -> Tuple[int, str]:
            """
            轮次排序函数：
            - 优先提取其中的数字部分（如 round10 -> 10），按数字升序
            - 若提取不到数字，则按原字符串排序
            """
            m = re.search(r"(\d+)", str(k))
            if m:
                return int(m.group(1)), str(k)
            return 0, str(k)
        
        # 按照“数字优先”的顺序遍历各轮
        for round_key in sorted(question_rounds.keys(), key=_round_sort_key):
            q_text = question_rounds.get(round_key, "")
            if not q_text:
                continue

            # 构造带上下文的问题：
            # - 前几轮的问答作为"对话历史"
            # - 当前轮的问题单独标出
            # 注意：格式要求已在 PROMPT_TEMPLATE 中统一说明，这里不需要额外添加
            if history_segments:
                history_text = "\n".join(history_segments)
                round_question = (
                    f"下面是我们之前的对话历史（供你参考，不要重复回答）：\n"
                    f"{history_text}\n\n"
                    f"现在是新的轮次 {round_key}，请只回答本轮问题：\n{q_text}"
                )
            else:
                # 第一轮：直接使用问题文本
                round_question = f"{round_key}：{q_text}"

            print(f"    [多轮] 模型{model_num} ({api_config_name}) -> {round_key}")

            ans, proc, rt, raw, final_prompt = self.get_model_answer(
                model_num=model_num,
                api_config_name=api_config_name,
                enabled=enabled,
                question=round_question,
                image_path=image_path,
            )

            answers[round_key] = ans
            processes[round_key] = proc
            total_time += rt
            last_raw_json = raw
            last_final_prompt = final_prompt  # 保存最后一轮的完整提示词
            
            # 记录每一轮的模型原始响应到日志（多轮问题在这里记录）
            if raw is not None:
                try:
                    # 使用当前问题ID和轮次，传入完整的最终提示词
                    log_model_response(
                        question_id=f"{question_id}_{round_key}",
                        question_num=question_num,
                        model_num=model_num,
                        model_name=api_config_name,
                        response=raw,
                        prompt=final_prompt  # 使用完整的最终提示词，而不是 question 预览
                    )
                except Exception as e:
                    if self.debug_mode:
                        print(f"      ⚠️ 记录日志失败 ({round_key}): {e}")

            # 将本轮问答加入历史，供后续轮次参考
            history_piece = f"{round_key} 问题：{q_text}\n{round_key} 你的回答：{ans}"
            history_segments.append(history_piece)

        # ---- 返回字典格式，保证每个 round 都是独立的 ----
        # 多轮题返回字典格式，与 question 和 answer 的格式保持一致
        final_answer = answers if answers else {}
        final_process = processes if processes else {}

        return final_answer, final_process, total_time, last_raw_json, last_final_prompt
    
    def compare_three_models(self, qa_item: Dict) -> Dict:
        """
        对比三个模型的答案（并行调用以提高速度）
        
        Args:
            qa_item: 包含 Q, Answer (GT), image_path 等的字典
                    如果 qa_item 中已包含 model1/model2/model3 字段且有有效答案，则跳过该模型的调用
        
        Returns:
            更新后的qa_item，包含三个模型的答案和对比结果
        """
        question = qa_item.get("Q", "")
        question_rounds = qa_item.get("Q_rounds", None)
        is_multi_round = isinstance(question_rounds, dict)
        gt_answer = qa_item.get("Answer", "")  # GT答案
        image_path = qa_item.get("image_path", "")
        question_id = qa_item.get("id", qa_item.get("question_id", "unknown"))  # 获取问题ID用于日志
        
        # 保存当前问题ID（用于多轮问题的日志记录）
        self.current_question_id = str(question_id)
        
        # 增加问题计数
        self.question_count += 1
        is_first_question = (self.question_count == 1)
        
        # 记录问题开始（用于日志顺序）
        log_question_start(question_id=str(question_id), question_num=self.question_count, 
                          is_multi_round=is_multi_round, question_preview=str(question_rounds if is_multi_round else question)[:200])
        
        # 检查是否已有结果（用于错误重试）
        existing_results = {}
        for model_num in [1, 2, 3]:
            model_key = f"model{model_num}"
            if model_key in qa_item and isinstance(qa_item[model_key], dict):
                existing_answer = qa_item[model_key].get("answer", "")
                # 检查是否有有效答案
                if existing_answer and (isinstance(existing_answer, str) and existing_answer.strip()) or \
                   (isinstance(existing_answer, dict) and existing_answer):
                    existing_results[model_num] = qa_item[model_key]
                    print(f"    模型{model_num} 已有结果，跳过调用")
        
        # ========== 并行调用三个模型 ==========
        need_call = False
        tasks = []
        if self.model1_enabled and 1 not in existing_results:
            tasks.append((1, self.model1_api_config_name, "模型1"))
            need_call = True
        if self.model2_enabled and 2 not in existing_results:
            tasks.append((2, self.model2_api_config_name, "模型2"))
            need_call = True
        if self.model3_enabled and 3 not in existing_results:
            tasks.append((3, self.model3_api_config_name, "模型3"))
            need_call = True
        
        if need_call:
            print(f"    并行调用 {len(tasks)} 个模型...")
        
        start_time = time.time()
        
        # 使用线程池并行执行
        results = {}
        
        # 先添加已有结果
        for model_num, existing_data in existing_results.items():
            results[model_num] = {
                "answer": existing_data.get("answer", ""),
                "process": existing_data.get("process", ""),
                "response_time": existing_data.get("response_time", 0.0),
                "raw_response_json": None,
                "final_prompt": ""
            }
        
        # 调用需要处理的模型
        if tasks:
            with ThreadPoolExecutor(max_workers=3) as executor:
                # 提交所有任务
                future_to_model = {}
                for model_num, api_config_name, model_name in tasks:
                    print(f"    提交{model_name}任务 (api_config: {api_config_name})...")
                    if is_multi_round:
                        # 多轮题：格式要求已在 PROMPT_TEMPLATE 中统一说明，不需要额外传递
                        future = executor.submit(
                            self.get_model_answer_multi_round,
                            model_num, api_config_name, True, question_rounds, image_path, 
                            str(question_id), self.question_count, ""
                        )
                    else:
                        future = executor.submit(
                            self.get_model_answer,
                            model_num, api_config_name, True, question, image_path
                        )
                    future_to_model[future] = (model_num, model_name)
                
                # 收集结果
                for future in as_completed(future_to_model):
                    model_num, model_name = future_to_model[future]
                    try:
                        result = future.result()
                        # 处理返回值：可能是 (answer, process, response_time, raw_json) 或 (answer, process, response_time, raw_json, final_prompt)
                        if len(result) >= 4:
                            answer = result[0]
                            process = result[1]
                            response_time = result[2]
                            raw_response_json = result[3]
                            final_prompt = result[4] if len(result) > 4 else str(question)  # 完整的最终提示词
                        else:
                            # 兼容旧格式
                            answer, process, response_time, raw_response_json = result[:4]
                            final_prompt = str(question)
                        
                        results[model_num] = {
                            "answer": answer,
                            "process": process,
                            "response_time": response_time,
                            "raw_response_json": raw_response_json,
                            "final_prompt": final_prompt  # 保存完整提示词
                        }
                        
                        # 记录模型原始响应到日志（单轮问题在这里记录）
                        if raw_response_json is not None and not is_multi_round:
                            try:
                                api_config_name = self.model1_api_config_name if model_num == 1 else (self.model2_api_config_name if model_num == 2 else self.model3_api_config_name)
                                log_model_response(
                                    question_id=str(question_id),
                                    question_num=self.question_count,
                                    model_num=model_num,
                                    model_name=api_config_name,
                                    response=raw_response_json,
                                    prompt=final_prompt  # 使用完整的最终提示词
                                )
                            except Exception as e:
                                if self.debug_mode:
                                    print(f"      ⚠️ 记录日志失败 ({model_name}): {e}")
                        
                        print(f"    {model_name}完成，耗时: {response_time:.2f}秒")
                    except Exception as e:
                        print(f"    {model_name}调用失败: {e}")
                        results[model_num] = {
                            "answer": "",
                            "process": "",
                            "response_time": 0.0,
                            "raw_response_json": None
                        }
        
        total_time = time.time() - start_time
        if need_call:
            print(f"    模型调用完成，总耗时: {total_time:.2f}秒")
        
        # 提取结果
        # 注意：多轮题返回字典格式，单轮题返回字符串格式
        answer1 = results.get(1, {}).get("answer", "" if not is_multi_round else {})
        process1 = results.get(1, {}).get("process", "" if not is_multi_round else {})
        time1 = results.get(1, {}).get("response_time", 0.0)
        raw_json1 = results.get(1, {}).get("raw_response_json", None)
        
        answer2 = results.get(2, {}).get("answer", "" if not is_multi_round else {})
        process2 = results.get(2, {}).get("process", "" if not is_multi_round else {})
        time2 = results.get(2, {}).get("response_time", 0.0)
        raw_json2 = results.get(2, {}).get("raw_response_json", None)
        
        answer3 = results.get(3, {}).get("answer", "" if not is_multi_round else {})
        process3 = results.get(3, {}).get("process", "" if not is_multi_round else {})
        time3 = results.get(3, {}).get("response_time", 0.0)
        raw_json3 = results.get(3, {}).get("raw_response_json", None)
        
        # 注意：final_prompt 已在日志记录时使用，这里不需要提取
        
        # 如果是第一个问题，打印三个模型的原始JSON响应
        if is_first_question:
            print("\n" + "=" * 80)
            print("📋 第一个问题的原始API响应JSON:")
            print("=" * 80)
            
            if raw_json1 is not None:
                print("\n【模型1 原始响应JSON】")
                print(json.dumps(raw_json1, ensure_ascii=False, indent=2))
            else:
                print("\n【模型1 原始响应JSON】: 无（可能调用失败或流式输出）")
            
            if raw_json2 is not None:
                print("\n【模型2 原始响应JSON】")
                print(json.dumps(raw_json2, ensure_ascii=False, indent=2))
            else:
                print("\n【模型2 原始响应JSON】: 无（可能调用失败或流式输出）")
            
            if raw_json3 is not None:
                print("\n【模型3 原始响应JSON】")
                print(json.dumps(raw_json3, ensure_ascii=False, indent=2))
            else:
                print("\n【模型3 原始响应JSON】: 无（可能调用失败或流式输出）")
            
            print("=" * 80 + "\n")
        
        # 保存模型答案（统一格式，使用自定义模型名称）
        # 统一使用 process 字段，不再使用 cot（保持向后兼容但标准化为 process）
        # 多轮题：answer 和 process 为字典格式；单轮题：为字符串格式
        # 直接使用提取的值，get 方法已经提供了正确的默认值
        qa_item["model1"] = {
            "enabled": self.model1_enabled,
            "answer": answer1,
            "process": process1,
            "model_name": self.model1_api_config_name or "",
            "response_time": time1 if time1 > 0 else 0.0
        }
        
        qa_item["model2"] = {
            "enabled": self.model2_enabled,
            "answer": answer2,
            "process": process2,
            "model_name": self.model2_api_config_name or "",
            "response_time": time2 if time2 > 0 else 0.0
        }
        
        qa_item["model3"] = {
            "enabled": self.model3_enabled,
            "answer": answer3,
            "process": process3,
            "model_name": self.model3_api_config_name or "",
            "response_time": time3 if time3 > 0 else 0.0
        }
        
        # 只统计启用的模型
        enabled_answers = []
        if self.model1_enabled:
            enabled_answers.append(answer1)
        if self.model2_enabled:
            enabled_answers.append(answer2)
        if self.model3_enabled:
            enabled_answers.append(answer3)
        
        # 对比结果：只统计与GT一致的模型数量
        agreement_count = count_agreement(enabled_answers, gt_answer) if enabled_answers and gt_answer else 0
        
        qa_item["comparison"] = {
            "agreement_with_gt": agreement_count
        }
        
        return qa_item

