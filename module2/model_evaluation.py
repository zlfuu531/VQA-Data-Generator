"""
模块2：模型评估模块 (Refactored for Config Integration)
功能：调用三方模型 -> 答案比对 (Judge) -> 难度分级 (Classifier)
特点：完全基于 config.py 驱动，支持多线程、断点续传、JSONL支持
"""
import os
import sys
import argparse
import time
import json
import re
import threading
import signal
import atexit
from datetime import datetime
from typing import List, Dict, Optional, Set
from concurrent.futures import ThreadPoolExecutor, as_completed

# 尝试导入 tqdm 用于显示进度条
try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 导入配置（仅模型与裁判模型相关配置）
from module2.config import MODEL_CONFIG
from utils import ensure_dir, load_json, save_json
from module2.answer_comparison import AnswerComparison
from module2.classifier import QAClassifier
from module2.judge import judge_answer_with_model
from module2.logger import init_log_file, log_model_response, close_log_file

DEFAULT_PROCESSING_CONFIG = {
    "max_workers": 4,   # 并发线程数
    "batch_size": 4,    # 批量保存大小
    "debug_mode": False # 是否打印更多调试信息
}

# 模型键列表（避免在多处重复）
MODEL_KEYS = ["model1", "model2", "model3"]

# 难度级别列表
DIFFICULTY_LEVELS = ["L1", "L2", "L3", "L4"]

# 线程锁
file_lock = threading.Lock()

class Module2ModelEvaluation:
    """模块2：模型评估器"""
    
    def __init__(
        self,
        output_dir: Optional[str] = None,
        max_workers: Optional[int] = None,
        batch_size: Optional[int] = None,
        debug_mode: Optional[bool] = None,
    ):
        """
        初始化模型评估器
        """
        # 1. 确定输出目录：优先使用参数，否则默认 <project_root>/output/module2
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        default_output_dir = os.path.join(project_root, "output", "module2")
        self.output_dir = output_dir if output_dir else default_output_dir
        ensure_dir(self.output_dir)
        
        # 运行参数（可由命令行覆盖）
        self.max_workers = max_workers if max_workers is not None else DEFAULT_PROCESSING_CONFIG["max_workers"]
        self.batch_size = batch_size if batch_size is not None else DEFAULT_PROCESSING_CONFIG["batch_size"]
        self.debug_mode = debug_mode if debug_mode is not None else DEFAULT_PROCESSING_CONFIG["debug_mode"]

        # 初始化子模块
        self.answer_comparison = AnswerComparison(debug_mode=self.debug_mode)  # 负责模型调用
        self.classifier = QAClassifier()  # 负责分级
        
        # 日志文件路径（将在 batch_evaluate 中初始化）
        self.log_file_path = None
        
        # 中断保存相关变量
        self._final_results_for_save = []  # 存储待保存的结果
        self._retry_results_for_save = []  # 存储待保存的重试结果
        self._output_file_for_save = None  # 输出文件路径（用于保存）
        self._out_dir_for_save = None  # 输出目录（用于保存）
        self._saved_result_ids_for_save = set()  # 已保存的结果ID
        self._shutdown_requested = False  # 是否请求关闭
        
        # 输出格式相关变量
        self._output_format = "jsonl"  # 输出格式：json 或 jsonl（根据文件扩展名自动判断）
        self._result_buffer = []  # JSON 格式的批量写入缓冲区
        self._buffer_lock = threading.Lock()  # 缓冲区锁
    
    @staticmethod
    def _get_model_config(model_key: str) -> Dict:
        """
        安全获取模型配置
        
        Args:
            model_key: 模型键（"model1", "model2", "model3"）
        
        Returns:
            模型配置字典（如果不存在则返回空字典）
        """
        return MODEL_CONFIG.get(model_key, {})
    
    @staticmethod
    def _get_model_name(model_key: str) -> str:
        """
        获取模型名称
        
        Args:
            model_key: 模型键
        
        Returns:
            模型名称（如果不存在则返回空字符串）
        """
        return Module2ModelEvaluation._get_model_config(model_key).get("name", "")
    
    @staticmethod
    def _derive_output_dir(base_output_file: str) -> str:
        """
        从输出文件路径推导输出目录（与 _save_by_level_and_summary 逻辑一致）
        
        Args:
            base_output_file: 输出文件路径（如 "xxx.json"）
        
        Returns:
            输出目录路径（如 "xxx/"）
        """
        parent_dir = os.path.dirname(base_output_file)
        base_name = os.path.basename(base_output_file)
        if "." in base_name:
            name_part, _ = os.path.splitext(base_name)
        else:
            name_part = base_name
        return os.path.join(parent_dir, name_part)
    
    @staticmethod
    def _round_sort_key(k: str) -> tuple:
        """
        多轮问题排序键：优先按数字大小排序
        
        Args:
            k: 轮次键（如 "round1", "round10"）
        
        Returns:
            排序键元组 (数字, 原字符串)
        """
        m = re.search(r"(\d+)", str(k))
        if m:
            return int(m.group(1)), str(k)
        return 0, str(k)

    def _normalize_items(self, items: List[Dict]) -> List[Dict]:
        """
        将输入统一规范为基于 module1 输出字段的结构。
        约定：上游就是 module1 的输出：
        - image_id / image_path / image_type
        - question_id / question_type / question / options / answer / qa_make_process
        在此基础上，仅补充内部使用的 id 字段（等于 question_id）。
        
        注意：如果输入中没有 qa_make_process 字段，则保持为空（不添加或设为空字符串/空字典）。
        """
        normalized: List[Dict] = []
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                print(f"⚠️ 警告：第 {idx} 条数据不是字典，已跳过")
                continue

            # 严格按照 module1 输出结构要求：必须包含 question_id / question / answer
            if "question_id" in item and "question" in item and "answer" in item:
                new_item = dict(item)  # 浅拷贝，保留原始字段

                # 使用 question_id 作为唯一 id
                qid = item.get("question_id")
                if not qid:
                    print(f"⚠️ 警告：第 {idx} 条数据缺少 question_id，已跳过")
                    continue
                new_item["id"] = qid

                # 兼容字段名：如果上游只提供 GT，可以同步到 answer
                if (not new_item.get("answer")) and "GT" in item:
                    new_item["answer"] = item.get("GT", "")

                # 确保 image_path 字段存在（如果没有就置空字符串，后续逻辑会做容错）
                if "image_path" not in new_item:
                    new_item["image_path"] = ""

                # qa_make_process 字段：如果输入中没有，就保持为空（不添加）
                # 如果输入中有但为空，也保持原样
                # 这样输出时如果没有这个字段，就表示输入时就没有

                normalized.append(new_item)
                continue

            # 无法识别的结构：给出提示并跳过
            print(f"⚠️ 警告：第 {idx} 条数据缺少 module1 规范字段（question_id/question/answer），已跳过")
        return normalized

    def _load_data(self, file_path: str) -> List[Dict]:
        """
        智能加载数据，支持 json 和 jsonl
        """
        if not file_path:
            raise ValueError("输入文件路径不能为空")
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"输入文件不存在: {file_path}")
            
        if file_path.endswith('.jsonl'):
            data = []
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        item = json.loads(line)
                        # 验证必要字段
                        if not isinstance(item, dict):
                            print(f"警告：第 {line_num} 行不是有效的JSON对象，跳过")
                            continue
                        data.append(item)
                    except json.JSONDecodeError as e:
                        print(f"警告：第 {line_num} 行JSON解析失败: {e}，跳过")
                        continue
            if not data:
                raise ValueError(f"JSONL文件 {file_path} 中没有有效数据")
            return self._normalize_items(data)
        else:
            # 假设是标准 JSON
            try:
                content = load_json(file_path)
            except Exception as e:
                raise ValueError(f"无法加载JSON文件 {file_path}: {e}")
            
            if isinstance(content, list):
                if not content:
                    raise ValueError(f"JSON文件 {file_path} 为空列表")
                return self._normalize_items(content)
            elif isinstance(content, dict) and "items" in content:
                items = content["items"]
                if not isinstance(items, list):
                    raise ValueError(f"JSON文件 {file_path} 中的 'items' 字段不是列表")
                if not items:
                    raise ValueError(f"JSON文件 {file_path} 中的 'items' 列表为空")
                return self._normalize_items(items)
            else:
                raise ValueError(f"无法解析 JSON 文件结构: {file_path}。期望格式：包含 'items' 字段的对象或JSON数组")

    def _build_model_question(self, item: Dict) -> str:
        """
        将 module1 的字段组装成适合下游模型回答的统一文本问题：
        - 支持单轮 & 多轮
        - 支持带 options 的选择题
        
        ⚠️ 提示词拼接流程说明：
        1. 单轮题：
           - 本方法构建完整问题文本（包含题型、图片类型、问题、选项、格式要求）
           - 返回的文本作为 question 参数传给 call_model*_api
           - call_model*_api 使用 PROMPT_TEMPLATE.format(question=question) 拼接
           - 最终提示词 = PROMPT_TEMPLATE + 本方法构建的问题文本
        
        2. 多轮题：
           - 本方法构建完整的多轮问题文本（包含所有 round 的问题和格式要求）
           - 但实际调用时，qa_item 中的 Q_rounds 是字典格式
           - 在 answer_comparison.py 的 get_model_answer_multi_round 中，每一轮单独构造 round_question
           - 第一轮：round_question = "round1：{问题文本}"（缺少格式要求！）
           - 后续轮：round_question = "历史对话\n\n现在是新的轮次 round2，请只回答本轮问题：{问题文本}"（缺少格式要求！）
           - 需要修复：在构造 round_question 时添加格式要求
        """
        image_type = item.get("image_type", "")
        qtype = item.get("question_type", "")
        question = item.get("question", "")
        options = item.get("options", None)

        parts = []
        if qtype:
            parts.append(f"【题型】{qtype}")
        if image_type:
            parts.append(f"【图片类型】{image_type}")

        # 多轮题：question 为 dict，形如 {"round1": "...", "round2": "..."}
        if isinstance(question, dict):
            parts.append("【多轮问题】")
            for rk in sorted(question.keys(), key=self._round_sort_key):
                q_text = question.get(rk, "")
                parts.append(f"{rk}：{q_text}")

            # 多轮选项（如多轮单选题）
            if isinstance(options, dict):
                parts.append("【多轮选项】")
                for rk in sorted(options.keys(), key=self._round_sort_key):
                    opt_dict = options.get(rk, {})
                    if isinstance(opt_dict, dict):
                        opt_str = "；".join([f"{k}: {v}" for k, v in opt_dict.items()])
                        parts.append(f"{rk} 选项：{opt_str}")
        else:
            # 单轮问题
            parts.append(f"【问题】{question}")

            # 单轮选项：单选 / 多选 / 判断
            if isinstance(options, dict):
                opt_str = "；".join([f"{k}: {v}" for k, v in options.items()])
                parts.append(f"【选项】{opt_str}")

        return "\n".join(parts)

    def step1_call_models(self, item: Dict, skip_existing: bool = False) -> Dict:
        """
        步骤1：调用三个模型获取答案
        
        Args:
            item: 数据项
            skip_existing: 是否跳过已有结果的模型（用于错误重试）
        """
        question = item.get("question", "")

        # 单轮题：直接构造统一文本问题
        if not isinstance(question, dict):
            qa_item = {
                "Q": self._build_model_question(item),
                "Answer": item.get("answer", ""),  # GT答案（字符串）
                "image_path": item.get("image_path", ""),
                "id": item.get("id", item.get("question_id", "unknown"))  # 传入问题ID用于日志
            }
        else:
            # 多轮题：按轮提问，不一次问完
            # 构建完整的问题文本（包含格式要求），用于提取格式要求部分
            full_question_text = self._build_model_question(item)
            qa_item = {
                "Q": full_question_text,            # 完整问题文本（包含格式要求），用于提取格式要求
                "Q_rounds": question,              # {"round1": "...", "round2": "..."}，实际的问题内容
                "Answer": item.get("answer", ""),  # GT答案（多轮 dict）
                "image_path": item.get("image_path", ""),
                "id": item.get("id", item.get("question_id", "unknown"))  # 传入问题ID用于日志
            }
        
        # 如果开启了跳过已有结果的模式，传递已有的模型结果
        if skip_existing:
            for key in MODEL_KEYS:
                if key in item and isinstance(item[key], dict):
                    # 检查是否有有效的答案
                    existing_answer = item[key].get("answer", "")
                    if existing_answer and (isinstance(existing_answer, str) or isinstance(existing_answer, dict)):
                        # 传递已有结果到 qa_item，AnswerComparison 会跳过已有结果的模型
                        qa_item[key] = item[key]
        
        # 调用 AnswerComparison 模块
        # 注意：AnswerComparison 内部应该也读取了 config 来决定调用哪些模型
        # 这里我们做二次校验和格式化
        compared_item = self.answer_comparison.compare_three_models(qa_item)
        
        result = item.copy()
        
        # 判断是否是多轮题
        is_multi_round = isinstance(question, dict)
        
        # 统一处理 model1, model2, model3
        for key in MODEL_KEYS:
            # 获取 config 中的开关状态
            config_enabled = self._get_model_config(key).get("enabled", False)
            
            # 获取模型返回的数据
            m_data = compared_item.get(key, {})
            
            # 只有当 config 启用且模型确实返回了数据时，才标记为 enabled
            is_actually_enabled = config_enabled and m_data.get("enabled", True)

            # 统一使用 process 字段（优先使用 process，如果没有则使用 cot 作为兼容）
            # 多轮题：process 为字典格式；单轮题：为字符串格式
            default_process = {} if is_multi_round else ""
            process_value = m_data.get("process", default_process)
            if not process_value and not is_multi_round:
                # 单轮题的兼容处理：尝试使用 cot 字段
                process_value = m_data.get("cot", "")
            
            # 多轮题：answer 为字典格式；单轮题：为字符串格式
            default_answer = {} if is_multi_round else ""
            answer_value = m_data.get("answer", default_answer)
            
            result[key] = {
                "enabled": is_actually_enabled,
                "process": process_value,
                "answer": answer_value,
                "model_name": m_data.get("model_name", self._get_model_name(key)),
                "response_time": m_data.get("response_time", 0.0),
                "match_gt": False  # 占位，步骤2计算
            }

        result["comparison"] = compared_item.get("comparison", {})
        return result
    
    def step2_compare_with_gt(self, item: Dict) -> Dict:
        """
        步骤2：使用评判模型 (Judge)
        """
        gt_answer = item.get("answer", "")
        question = item.get("question", "")
        image_path = item.get("image_path", "")
        options = item.get("options", None)
        is_multi_round = isinstance(question, dict) and isinstance(gt_answer, dict)
        
        # 验证必要字段
        if not question:
            print(f"⚠️ 警告：item {item.get('id', 'unknown')} 缺少 question 字段")
        if not gt_answer:
            print(f"⚠️ 警告：item {item.get('id', 'unknown')} 缺少 answer (GT) 字段")
        
        for model_key in MODEL_KEYS:
            model_data = item.get(model_key, {})
            
            # 确保 model_data 是字典
            if not isinstance(model_data, dict):
                print(f"⚠️ 警告：item {item.get('id', 'unknown')} 的 {model_key} 不是字典，初始化为空字典")
                model_data = {}
                item[model_key] = model_data
            
            # 仅评测已启用的模型
            if model_data.get("enabled", False):
                model_answer = model_data.get("answer", "")
                
                if not model_answer:
                    # 如果启用了但没答案（可能API错误），视为不匹配
                    model_data["match_gt"] = False
                    continue

                # 多轮题：每个 round 单独评判
                if is_multi_round:
                    # 模型答案应该是字典格式 {"round1": "答案1", "round2": "答案2"}
                    # 兼容处理：如果是字符串格式（旧数据），尝试解析
                    model_answers_dict = {}
                    if isinstance(model_answer, dict):
                        # 直接使用字典格式
                        model_answers_dict = model_answer
                    elif isinstance(model_answer, str):
                        # 兼容旧格式：解析字符串格式 "round1: 答案1; round2: 答案2"
                        print(f"      ⚠️ 警告：{model_key} 的答案格式为字符串，正在解析（应使用字典格式）")
                        for part in model_answer.split(";"):
                            part = part.strip()
                            if ":" in part:
                                round_key, answer = part.split(":", 1)
                                round_key = round_key.strip()
                                answer = answer.strip()
                                model_answers_dict[round_key] = answer
                    
                    # 对每个 round 进行评判
                    all_rounds_match = True
                    round_results = {}
                    for round_key in sorted(gt_answer.keys(), key=self._round_sort_key):
                        gt_round_answer = gt_answer.get(round_key, "")
                        model_round_answer = model_answers_dict.get(round_key, "")
                        round_question = question.get(round_key, "")
                        # 获取对应轮次的选项
                        round_options = None
                        if isinstance(options, dict):
                            round_options = options.get(round_key, None)
                        
                        if not model_round_answer:
                            all_rounds_match = False
                            round_results[round_key] = {
                                "match": False,
                                "reasoning": "模型答案中缺少该轮次的答案"
                            }
                            continue
                        
                        try:
                            is_match, judge_reasoning, judge_time = judge_answer_with_model(
                                model_answer=model_round_answer,
                                gt_answer=gt_round_answer,
                                question=round_question,
                                image_path=image_path,
                                options=round_options
                            )
                            round_results[round_key] = {
                                "match": is_match,
                                "reasoning": judge_reasoning,
                                "time": judge_time
                            }
                            if not is_match:
                                all_rounds_match = False
                        except Exception as e:
                            print(f"⚠️ 警告：评判模型调用失败 ({model_key}, {round_key}): {e}，使用字符串匹配作为降级方案")
                            from utils import compare_answers
                            is_match = compare_answers(model_round_answer, gt_round_answer)
                            round_results[round_key] = {
                                "match": is_match,
                                "reasoning": f"模型评判失败，已转为规则匹配: {str(e)}"
                            }
                            if not is_match:
                                all_rounds_match = False
                    
                    model_data["match_gt"] = all_rounds_match
                    # 保存每轮的评判结果（用于调试）
                    if self.debug_mode:
                        model_data["judge_reasoning"] = f"多轮评判结果: {round_results}"
                        # 计算总评判时间
                        total_judge_time = sum(r.get("time", 0) for r in round_results.values())
                        model_data["judge_time"] = total_judge_time
                else:
                    # 单轮题：直接评判
                    try:
                        is_match, judge_reasoning, judge_time = judge_answer_with_model(
                            model_answer=model_answer,
                            gt_answer=gt_answer,
                            question=question if isinstance(question, str) else str(question),
                            image_path=image_path,
                            options=options
                        )
                        
                        model_data["match_gt"] = is_match
                        # 可选字段：judge_reasoning 和 judge_time 用于调试，但不影响主流程
                        if self.debug_mode:
                            model_data["judge_reasoning"] = judge_reasoning
                            model_data["judge_time"] = judge_time
                    except Exception as e:
                        print(f"⚠️ 警告：评判模型调用失败 ({model_key}): {e}，使用字符串匹配作为降级方案")
                        # 降级到字符串匹配
                        from utils import compare_answers
                        model_data["match_gt"] = compare_answers(model_answer, gt_answer)
            else:
                # 未启用的模型
                model_data["match_gt"] = False
        
        return item
    
    def step3_classify(self, item: Dict) -> Dict:
        """
        步骤3：分级
        """
        # 构造 classifier 需要的输入格式
        qa_item = {
            "Q": item.get("question", ""),
            "Answer": item.get("answer", ""),
            "image_path": item.get("image_path", ""),
            "model1": item.get("model1", {}),
            "model2": item.get("model2", {}),
            "model3": item.get("model3", {}),
            "comparison": item.get("comparison", {})
        }
        
        classified = self.classifier.classify_qa_item(qa_item)
        item["classification"] = classified.get("classification", {})
        return item
    
    def _check_model_errors(self, item: Dict) -> Dict:
        """
        检查模型是否有出错的情况
        
        Returns:
            包含错误信息的字典，格式：{"has_error": bool, "error_models": [model_key, ...], "error_details": {...}}
        """
        error_info = {
            "has_error": False,
            "error_models": [],
            "error_details": {}
        }
        
        question = item.get("question", "")
        is_multi_round = isinstance(question, dict)
        
        for model_key in MODEL_KEYS:
            model_data = item.get(model_key, {})
            if not isinstance(model_data, dict):
                continue
            
            # 只检查启用的模型
            if not model_data.get("enabled", False):
                continue
            
            answer = model_data.get("answer", "")
            
            # 判断是否出错：启用了但没有答案，或者答案为空
            has_error = False
            error_detail = ""
            
            if is_multi_round:
                # 多轮题：answer 应该是字典格式
                if not isinstance(answer, dict) or not answer:
                    has_error = True
                    error_detail = "多轮题答案为空或格式错误"
            else:
                # 单轮题：answer 应该是字符串格式
                if not isinstance(answer, str) or not answer.strip():
                    has_error = True
                    error_detail = "单轮题答案为空"
            
            if has_error:
                error_info["has_error"] = True
                error_info["error_models"].append(model_key)
                error_info["error_details"][model_key] = error_detail
        
        return error_info
    
    def evaluate_item(self, item: Dict, retry_errors: bool = False) -> Dict:
        """
        单条数据处理流水线
        
        Args:
            item: 数据项
            retry_errors: 是否为错误重试模式（只调用之前出错的模型）
        """
        item_id = item.get("id", "unknown")
        
        # 验证必要字段
        required_fields = ["id", "question", "answer"]
        missing_fields = [f for f in required_fields if not item.get(f)]
        if missing_fields:
            error_msg = f"缺少必要字段: {missing_fields}"
            print(f"❌ Error processing item {item_id}: {error_msg}")
            item["error"] = error_msg
            return item
        
        try:
            # 1. 调用模型（如果是重试模式，跳过已有结果的模型）
            item = self.step1_call_models(item, skip_existing=retry_errors)
            
            # 检查是否有模型出错
            error_info = self._check_model_errors(item)
            if error_info["has_error"]:
                item["model_error"] = error_info
                print(f"⚠️  模型生成错误 (item {item_id}): {error_info['error_models']}")
                # 有模型出错，不进行后续的评判和分级，直接返回
                item = self._ensure_output_format(item, include_error=True)
                return item
            else:
                # 如果之前有错误标记，现在已解决，清除错误标记
                if "model_error" in item:
                    del item["model_error"]
            
            # 2. 评判
            item = self.step2_compare_with_gt(item)
            # 3. 分级
            item = self.step3_classify(item)
            
            # 确保输出格式符合规范
            item = self._ensure_output_format(item)
            
            return item
        except Exception as e:
            print(f"❌ Error processing item {item_id}: {str(e)}")
            if self.debug_mode:
                import traceback
                traceback.print_exc()
            item["error"] = str(e)
            # 即使出错也确保基本结构存在
            item = self._ensure_output_format(item, include_error=True)
            return item
    
    def _ensure_output_format(self, item: Dict, include_error: bool = False) -> Dict:
        """
        确保输出格式符合 data_schema.py 定义的规范
        """
        # 确保所有模型字段存在
        for model_key in MODEL_KEYS:
            if model_key not in item:
                item[model_key] = {
                    "enabled": False,
                    "process": "",
                    "answer": "",
                    "model_name": self._get_model_name(model_key),
                    "response_time": 0.0,
                    "match_gt": False
                }
            else:
                # 确保每个模型字段完整
                model_data = item[model_key]
                if not isinstance(model_data, dict):
                    model_data = {}
                    item[model_key] = model_data
                
                # 确保所有必需字段存在
                model_data.setdefault("enabled", False)
                model_data.setdefault("process", "")
                model_data.setdefault("answer", "")
                model_data.setdefault("model_name", self._get_model_name(model_key))
                model_data.setdefault("response_time", 0.0)
                model_data.setdefault("match_gt", False)
        
        # 确保 comparison 字段存在且完整
        if "comparison" not in item:
            item["comparison"] = {}
        
        comparison = item["comparison"]
        if not isinstance(comparison, dict):
            comparison = {}
            item["comparison"] = comparison
        
        # 确保所有必需字段存在
        comparison.setdefault("agreement_with_gt", 0)
        
        # 确保 classification 字段存在且完整
        if "classification" not in item:
            item["classification"] = {}
        
        classification = item["classification"]
        if not isinstance(classification, dict):
            classification = {}
            item["classification"] = classification
        
        # 确保所有必需字段存在（符合 data_schema.py 定义）
        # 支持 L1, L2, L3, L4 级别（不再有 L0）
        classification.setdefault("level", "L4")
        classification.setdefault("category", "处理失败" if include_error else "未分类")
        classification.setdefault("agreement_count", comparison.get("agreement_with_gt", 0))
        
        return item

    def _write_jsonl_item(self, item: Dict, level: str = None):
        """
        JSONL 格式：实时写入单条数据到对应级别的文件（逐行追加）
        
        Args:
            item: 要写入的数据项
            level: 难度级别（L1-L4）或 "error"，如果为 None 则根据 classification 自动判断
        """
        if self._output_format != "jsonl":
            return False
        
        if not self._out_dir_for_save:
            return False
        
        # 确定级别
        if level is None:
            if "model_error" in item or "error" in item:
                level = "error"
            else:
                level = item.get("classification", {}).get("level", "Unknown")
                if level not in DIFFICULTY_LEVELS:
                    level = "L4"
        
        # 确定文件路径
        if level == "error":
            file_path = os.path.join(self._out_dir_for_save, "error.jsonl")
        else:
            file_path = os.path.join(self._out_dir_for_save, f"{level}.jsonl")
        
        # 实时写入（线程安全）
        with file_lock:
            try:
                with open(file_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(item, ensure_ascii=False) + "\n")
                return True
            except Exception as e:
                print(f"❌ [JSONL实时写入失败] {e}")
                return False
    
    def _flush_buffer(self):
        """
        批量写入缓冲区数据到文件（仅用于 JSON 格式，JSONL 格式不使用此函数）
        """
        if self._output_format == "jsonl":
            return
        
        if not self._out_dir_for_save:
            return
        
        with self._buffer_lock:
            if not self._result_buffer:
                return
            current_batch = list(self._result_buffer)
            self._result_buffer = []
        
        try:
            # 按级别分类
            from collections import defaultdict
            level_buckets: Dict[str, List[Dict]] = defaultdict(list)
            error_items = []
            
            for item in current_batch:
                if "model_error" in item or "error" in item:
                    error_items.append(item)
                else:
                    level = item.get("classification", {}).get("level", "Unknown")
                    if level not in DIFFICULTY_LEVELS:
                        level = "L4"
                    level_buckets[level].append(item)
            
            # 使用线程锁保证线程安全地追加保存
            with file_lock:
                # 追加保存到各难度级别文件
                for lvl in DIFFICULTY_LEVELS:
                    new_items = level_buckets.get(lvl, [])
                    if not new_items:
                        continue
                    
                    lvl_path = os.path.join(self._out_dir_for_save, f"{lvl}.json")
                    # 读取现有数据
                    existing_items = []
                    if os.path.isfile(lvl_path):
                        try:
                            existing_data = load_json(lvl_path)
                            if isinstance(existing_data, list):
                                existing_items = existing_data
                        except Exception:
                            existing_items = []
                    
                    # 合并并去重（基于id）
                    existing_ids = {str(item.get("id", "")) for item in existing_items}
                    for item in new_items:
                        item_id = str(item.get("id", ""))
                        if item_id not in existing_ids:
                            existing_items.append(item)
                            existing_ids.add(item_id)
                    
                    # 保存更新后的文件
                    save_json(existing_items, lvl_path)
                
                # 追加保存错误结果
                if error_items:
                    error_path = os.path.join(self._out_dir_for_save, "error.json")
                    existing_errors = []
                    if os.path.isfile(error_path):
                        try:
                            existing_data = load_json(error_path)
                            if isinstance(existing_data, list):
                                existing_errors = existing_data
                        except Exception:
                            existing_errors = []
                    
                    # 合并并去重
                    existing_error_ids = {str(item.get("id", "")) for item in existing_errors}
                    for item in error_items:
                        item_id = str(item.get("id", ""))
                        if item_id not in existing_error_ids:
                            existing_errors.append(item)
                            existing_error_ids.add(item_id)
                    
                    save_json(existing_errors, error_path)
            
        except Exception as e:
            print(f"⚠️ [JSON批量保存失败] {e}")

    def _save_unsaved_results(self):
        """
        保存所有未保存的结果（用于中断时调用）
        这个方法可以在信号处理器、atexit 或异常处理中调用
        """
        if not self._out_dir_for_save:
            return
        
        # 合并所有待保存的结果
        all_unsaved = self._final_results_for_save.copy()
        all_unsaved.extend(self._retry_results_for_save)
        
        # JSONL 格式：还需要保存 buffer 中的结果
        if self._output_format == "jsonl":
            # JSONL 格式理论上已经实时写入，但为了安全起见，检查是否有未写入的
            # 实际上，JSONL 格式不需要这个函数，因为已经实时写入了
            # 但为了兼容，我们还是检查一下
            if all_unsaved:
                print("\n💾 正在保存未保存的结果（中断保护 - JSONL格式）...")
                saved_count = 0
                for res in all_unsaved:
                    res_id = str(res.get("id", ""))
                    if res_id and res_id not in self._saved_result_ids_for_save:
                        if self._write_jsonl_item(res):
                            self._saved_result_ids_for_save.add(res_id)
                            saved_count += 1
                if saved_count > 0:
                    print(f"✅ 已保存 {saved_count} 条未保存的结果到 {self._out_dir_for_save}")
                else:
                    print("   所有结果已保存，无需额外保存")
            return
        
        # JSON 格式：刷新 buffer 并保存
        if self._result_buffer:
            self._flush_buffer()
        
        if not all_unsaved:
            return
        
        try:
            print("\n💾 正在保存未保存的结果（中断保护）...")
            
            # 找出尚未保存的结果
            new_results_to_save = []
            for res in all_unsaved:
                res_id = str(res.get("id", ""))
                if res_id and res_id not in self._saved_result_ids_for_save:
                    new_results_to_save.append(res)
                    self._saved_result_ids_for_save.add(res_id)
            
            if not new_results_to_save:
                print("   所有结果已保存，无需额外保存")
                return
            
            # 分离正常结果和错误结果
            normal_to_save = []
            error_to_save = []
            for item in new_results_to_save:
                if "model_error" in item or "error" in item:
                    error_to_save.append(item)
                else:
                    normal_to_save.append(item)
            
            # 按难度级别分类正常结果
            from collections import defaultdict
            level_buckets: Dict[str, List[Dict]] = defaultdict(list)
            for item in normal_to_save:
                level = item.get("classification", {}).get("level", "Unknown")
                if level not in DIFFICULTY_LEVELS:
                    level = "L4"
                level_buckets[level].append(item)
            
            # 使用线程锁保证线程安全地追加保存
            with file_lock:
                file_ext = ".jsonl" if self._output_format == "jsonl" else ".json"
                
                # 追加保存到各难度级别文件
                for lvl in DIFFICULTY_LEVELS:
                    new_items = level_buckets.get(lvl, [])
                    if not new_items:
                        continue
                    
                    lvl_path = os.path.join(self._out_dir_for_save, f"{lvl}{file_ext}")
                    
                    if self._output_format == "jsonl":
                        # JSONL 格式：逐行追加
                        with open(lvl_path, "a", encoding="utf-8") as f:
                            for item in new_items:
                                item_id = str(item.get("id", ""))
                                if item_id and item_id not in self._saved_result_ids_for_save:
                                    f.write(json.dumps(item, ensure_ascii=False) + "\n")
                                    self._saved_result_ids_for_save.add(item_id)
                    else:
                        # JSON 格式：读取现有数据
                        existing_items = []
                        if os.path.isfile(lvl_path):
                            try:
                                existing_data = load_json(lvl_path)
                                if isinstance(existing_data, list):
                                    existing_items = existing_data
                            except Exception:
                                existing_items = []
                        
                        # 合并并去重（基于id）
                        existing_ids = {str(item.get("id", "")) for item in existing_items}
                        for item in new_items:
                            item_id = str(item.get("id", ""))
                            if item_id not in existing_ids:
                                existing_items.append(item)
                                existing_ids.add(item_id)
                        
                        # 保存更新后的文件
                        save_json(existing_items, lvl_path)
                
                # 追加保存错误结果
                if error_to_save:
                    error_path = os.path.join(self._out_dir_for_save, f"error{file_ext}")
                    
                    if self._output_format == "jsonl":
                        # JSONL 格式：逐行追加
                        with open(error_path, "a", encoding="utf-8") as f:
                            for item in error_to_save:
                                item_id = str(item.get("id", ""))
                                if item_id and item_id not in self._saved_result_ids_for_save:
                                    f.write(json.dumps(item, ensure_ascii=False) + "\n")
                                    self._saved_result_ids_for_save.add(item_id)
                    else:
                        # JSON 格式：读取现有数据
                        existing_errors = []
                        if os.path.isfile(error_path):
                            try:
                                existing_data = load_json(error_path)
                                if isinstance(existing_data, list):
                                    existing_errors = existing_data
                            except Exception:
                                existing_errors = []
                        
                        # 合并并去重
                        existing_error_ids = {str(item.get("id", "")) for item in existing_errors}
                        for item in error_to_save:
                            item_id = str(item.get("id", ""))
                            if item_id not in existing_error_ids:
                                existing_errors.append(item)
                                existing_error_ids.add(item_id)
                        
                        save_json(existing_errors, error_path)
            
            saved_count = len(new_results_to_save)
            print(f"✅ 已保存 {saved_count} 条未保存的结果到 {self._out_dir_for_save}")
            
        except Exception as e:
            print(f"❌ 保存未保存结果失败: {e}")
            if self.debug_mode:
                import traceback
                traceback.print_exc()

    def _load_existing_results(self, output_dir: str) -> tuple:
        """
        从已有的 L1-L4.json/jsonl 和 error.json/jsonl 中加载历史结果，用于断点续传/增量追加。
        
        Args:
            output_dir: 输出目录路径
        
        Returns:
            (历史结果列表, 错误结果列表) 元组
        """
        if not os.path.isdir(output_dir):
            return [], []
        
        # 使用实例的输出格式
        is_jsonl = (self._output_format == "jsonl")
        
        # 加载正常结果
        existing_results: List[Dict] = []
        for lvl in DIFFICULTY_LEVELS:
            if is_jsonl:
                path = os.path.join(output_dir, f"{lvl}.jsonl")
            else:
                path = os.path.join(output_dir, f"{lvl}.json")
            
            if not os.path.isfile(path):
                continue
            try:
                if is_jsonl:
                    # JSONL 格式：逐行读取
                    with open(path, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                item = json.loads(line)
                                if isinstance(item, dict):
                                    existing_results.append(item)
                            except json.JSONDecodeError:
                                continue
                else:
                    # JSON 格式：标准读取
                    data = load_json(path)
                    if isinstance(data, list):
                        existing_results.extend(data)
            except Exception as e:
                print(f"⚠️ 读取历史结果文件失败（{path}）: {e}")
        
        # 加载错误结果
        error_results: List[Dict] = []
        if is_jsonl:
            error_path = os.path.join(output_dir, "error.jsonl")
        else:
            error_path = os.path.join(output_dir, "error.json")
        
        if os.path.isfile(error_path):
            try:
                if is_jsonl:
                    # JSONL 格式：逐行读取
                    with open(error_path, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                item = json.loads(line)
                                if isinstance(item, dict):
                                    error_results.append(item)
                            except json.JSONDecodeError:
                                continue
                else:
                    # JSON 格式：标准读取
                    data = load_json(error_path)
                    if isinstance(data, list):
                        error_results = data
                if error_results:
                    print(f"🔄 检测到错误文件 {error_path}，错误样本数: {len(error_results)}")
            except Exception as e:
                print(f"⚠️ 读取错误结果文件失败（{error_path}）: {e}")
        
        if existing_results:
            print(f"🔁 检测到已有输出目录 {output_dir}，历史样本数: {len(existing_results)}")
        
        return existing_results, error_results

    def batch_evaluate(self, input_file: Optional[str] = None, output_dir: Optional[str] = None, 
                       output_format: str = "json", re_evaluate: bool = False):
        """
        批量评估主入口
        
        Args:
            input_file: 输入文件路径（支持 .json 和 .jsonl 格式）
            output_dir: 输出目录路径（文件夹路径，不需要文件名）
            output_format: 输出格式，json 或 jsonl（默认：json）
            re_evaluate: 是否重新评估（跳过断点续传，生成新版本文件）
        """
        # 1. 路径解析
        if input_file is None:
            raise ValueError(
                "未指定输入文件。请通过命令行参数 --input <file_path> 提供 "
                "（支持 .json 和 .jsonl 格式）。"
            )
        
        # 验证输出格式
        if output_format not in ["json", "jsonl"]:
            raise ValueError(f"输出格式必须是 'json' 或 'jsonl'，当前为: {output_format}")
        
        # 设置输出格式
        self._output_format = output_format
        
        if output_dir is None:
            # 默认输出到 <output_dir>/module2_result
            output_dir = os.path.join(self.output_dir, "module2_result")
        
        # 确保输出路径是绝对路径
        if not os.path.isabs(output_dir):
            # 如果是相对路径，基于项目根目录
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            output_dir = os.path.join(project_root, output_dir.lstrip("./"))
        
        # 确保输出目录存在
        ensure_dir(output_dir)
        
        # 初始化日志文件
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        log_dir = os.path.join(project_root, "module2_logs")
        self.log_file_path = init_log_file(
            log_dir=log_dir,
            input_file=input_file,
            output_file=output_dir,  # 使用目录路径
            max_workers=self.max_workers,
            batch_size=self.batch_size,
            debug_mode=self.debug_mode
        )
        print(f"📝 [日志] 日志文件: {self.log_file_path}")
        
        print("=" * 60)
        print(f"🚀 模块2：模型评估启动")
        print(f"📂 输入: {input_file}")
        print(f"💾 输出目录: {output_dir}")
        print(f"📝 输出格式: {output_format}")
        print(f"⚙️  并发: {self.max_workers} | Batch: {self.batch_size}")
        print("=" * 60)

        # 2. 加载输入数据
        try:
            all_items = self._load_data(input_file)
        except Exception as e:
            print(f"❌ 无法加载输入文件: {e}")
            return
        
        # 3. 根据是否 re_evaluate 决定是否增量处理
        existing_results: List[Dict] = []
        error_results: List[Dict] = []
        processed_ids: Set[str] = set()

        if not re_evaluate:
            # 非重新评估模式：如果已有输出目录，则按 id 跳过已处理样本，并加载错误结果
            existing_results, error_results = self._load_existing_results(output_dir)
            for r in existing_results:
                rid = r.get("id")
                if rid is not None:
                    processed_ids.add(str(rid))
            if processed_ids:
                print(f"🔎 已处理样本数（根据 id 去重）: {len(processed_ids)}")

        # 处理待处理的新样本
        if processed_ids:
            pending_items = [item for item in all_items if str(item.get("id")) not in processed_ids]
        else:
            pending_items = all_items

        print(f"📊 总数: {len(all_items)} | 已处理: {len(processed_ids)} | 新增待处理: {len(pending_items)} | 错误重试: {len(error_results)}")
        
        # 4. 并发执行新样本
        final_results: List[Dict] = []
        max_workers = self.max_workers
        
        # 使用输出目录（直接使用，不需要推导）
        out_dir = output_dir
        ensure_dir(out_dir)
        
        # 输出格式提示
        if self._output_format == "jsonl":
            print(f"📝 [输出格式] 使用 JSONL 格式（实时逐行追加写入）")
            print(f"   💡 JSONL 格式优势：每条结果实时写入，无需buffer，batch参数不生效")
        else:
            print(f"📝 [输出格式] 使用 JSON 格式（批量保存，batch={self.batch_size}）")
            print(f"   💡 提示：如需处理大量数据，建议使用 .jsonl 格式（逐行追加，性能更好）")
        
        # 初始化中断保存相关变量
        self._final_results_for_save = final_results
        self._retry_results_for_save = []
        self._output_file_for_save = None  # 不再使用文件路径
        self._out_dir_for_save = out_dir
        self._saved_result_ids_for_save = set()
        self._shutdown_requested = False
        self._result_buffer = []  # 重置缓冲区
        
        # 设置信号处理器（用于捕获 Ctrl+C 等中断信号）
        def signal_handler(signum, frame):
            """处理中断信号"""
            if self._shutdown_requested:
                # 如果已经请求过关闭，强制退出
                print("\n\n⚠️  强制退出...")
                sys.exit(1)
            
            self._shutdown_requested = True
            print("\n\n⚠️  检测到中断信号（Ctrl+C），正在保存已处理的数据...")
            self._save_unsaved_results()
            print("✅ 数据已保存，正在退出...")
            sys.exit(0)
        
        # 注册信号处理器（SIGINT: Ctrl+C, SIGTERM: 终止信号）
        original_sigint = signal.signal(signal.SIGINT, signal_handler)
        original_sigterm = signal.signal(signal.SIGTERM, signal_handler)
        
        # 注册退出时的保存函数（作为额外保障）
        def exit_handler():
            """程序退出时的清理函数"""
            if not self._shutdown_requested:
                self._save_unsaved_results()
        
        atexit.register(exit_handler)
        
        # 跟踪已保存的结果ID，避免重复保存
        saved_result_ids: Set[str] = set()
        
        def save_checkpoint():
            """
            批量保存中间结果到 L1-L4.json 和 error.json，实现真正的断点续传。
            只保存本次批量处理中新增的结果，避免重复保存。
            """
            # 同步更新实例变量，以便信号处理器可以访问
            self._final_results_for_save = final_results
            self._saved_result_ids_for_save = saved_result_ids
            
            if not final_results:
                return
            
            # 找出本次批量中尚未保存的结果
            new_results_to_save = []
            for res in final_results:
                res_id = str(res.get("id", ""))
                if res_id and res_id not in saved_result_ids:
                    new_results_to_save.append(res)
                    saved_result_ids.add(res_id)
            
            if not new_results_to_save:
                return
            
            # 同步更新已保存的ID
            self._saved_result_ids_for_save = saved_result_ids
            
            try:
                # 分离正常结果和错误结果
                normal_to_save = []
                error_to_save = []
                for item in new_results_to_save:
                    if "model_error" in item or "error" in item:
                        error_to_save.append(item)
                    else:
                        normal_to_save.append(item)
                
                # 按难度级别分类正常结果
                from collections import defaultdict
                level_buckets: Dict[str, List[Dict]] = defaultdict(list)
                for item in normal_to_save:
                    level = item.get("classification", {}).get("level", "Unknown")
                    if level not in DIFFICULTY_LEVELS:
                        level = "L4"
                    level_buckets[level].append(item)
                
                # 使用线程锁保证线程安全地追加保存
                with file_lock:
                    file_ext = ".jsonl" if self._output_format == "jsonl" else ".json"
                    
                    # 追加保存到各难度级别文件
                    for lvl in DIFFICULTY_LEVELS:
                        new_items = level_buckets.get(lvl, [])
                        if not new_items:
                            continue
                        
                        lvl_path = os.path.join(out_dir, f"{lvl}{file_ext}")
                        
                        if self._output_format == "jsonl":
                            # JSONL 格式：逐行追加
                            with open(lvl_path, "a", encoding="utf-8") as f:
                                for item in new_items:
                                    item_id = str(item.get("id", ""))
                                    if item_id and item_id not in saved_result_ids:
                                        f.write(json.dumps(item, ensure_ascii=False) + "\n")
                                        saved_result_ids.add(item_id)
                        else:
                            # JSON 格式：读取现有数据
                            existing_items = []
                            if os.path.isfile(lvl_path):
                                try:
                                    existing_data = load_json(lvl_path)
                                    if isinstance(existing_data, list):
                                        existing_items = existing_data
                                except Exception:
                                    existing_items = []
                            
                            # 合并并去重（基于id）
                            existing_ids = {str(item.get("id", "")) for item in existing_items}
                            for item in new_items:
                                item_id = str(item.get("id", ""))
                                if item_id not in existing_ids:
                                    existing_items.append(item)
                                    existing_ids.add(item_id)
                            
                            # 保存更新后的文件
                            save_json(existing_items, lvl_path)
                    
                    # 追加保存错误结果
                    if error_to_save:
                        error_path = os.path.join(out_dir, f"error{file_ext}")
                        
                        if self._output_format == "jsonl":
                            # JSONL 格式：逐行追加
                            with open(error_path, "a", encoding="utf-8") as f:
                                for item in error_to_save:
                                    item_id = str(item.get("id", ""))
                                    if item_id and item_id not in saved_result_ids:
                                        f.write(json.dumps(item, ensure_ascii=False) + "\n")
                                        saved_result_ids.add(item_id)
                        else:
                            # JSON 格式：读取现有数据
                            existing_errors = []
                            if os.path.isfile(error_path):
                                try:
                                    existing_data = load_json(error_path)
                                    if isinstance(existing_data, list):
                                        existing_errors = existing_data
                                except Exception:
                                    existing_errors = []
                            
                            # 合并并去重
                            existing_error_ids = {str(item.get("id", "")) for item in existing_errors}
                            for item in error_to_save:
                                item_id = str(item.get("id", ""))
                                if item_id not in existing_error_ids:
                                    existing_errors.append(item)
                                    existing_error_ids.add(item_id)
                            
                            save_json(existing_errors, error_path)
                
                saved_count = len(new_results_to_save)
                print(f"💾 批量保存检查点: {saved_count} 条结果已保存到 {out_dir}")
                
            except Exception as e:
                print(f"⚠️ 批量保存检查点失败: {e}")

        try:
            if pending_items:
                print("\n🔄 处理新样本...")
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    future_to_item = {executor.submit(self.evaluate_item, item, False): item for item in pending_items}
                    
                    pbar = tqdm(total=len(pending_items), desc="Processing New", unit="q") if tqdm else None
                    
                    completed_in_session = 0
                    for future in as_completed(future_to_item):
                        # 检查是否请求关闭
                        if self._shutdown_requested:
                            print("\n⚠️  检测到关闭请求，正在停止处理新任务...")
                            # 取消未完成的任务
                            for f in future_to_item:
                                f.cancel()
                            break
                        
                        res = future.result()
                        final_results.append(res)
                        # 同步更新实例变量
                        self._final_results_for_save = final_results
                        
                        completed_in_session += 1
                        
                        # 根据输出格式选择保存方式
                        if self._output_format == "jsonl":
                            # JSONL 格式：实时写入
                            self._write_jsonl_item(res)
                            res_id = str(res.get("id", ""))
                            if res_id:
                                saved_result_ids.add(res_id)
                        else:
                            # JSON 格式：加入 buffer
                            with self._buffer_lock:
                                self._result_buffer.append(res)
                                # 当 buffer 达到 batch_size 时，批量写入
                                if len(self._result_buffer) >= self.batch_size:
                                    self._flush_buffer()
                        
                        # JSON 格式的批量保存检查点（用于统计和最终保存）
                        if self._output_format == "json" and completed_in_session % self.batch_size == 0:
                            save_checkpoint()
                        
                        if pbar: pbar.update(1)
                    
                    # 处理完成后，保存剩余的结果
                    if self._output_format == "json":
                        # JSON 格式：刷新 buffer 和保存检查点
                        self._flush_buffer()
                        if final_results:
                            save_checkpoint()
                    # JSONL 格式：已经实时写入，无需额外保存
                    
                    if pbar: pbar.close()
        except KeyboardInterrupt:
            # 捕获键盘中断（虽然信号处理器应该已经处理了，但作为额外保障）
            if not self._shutdown_requested:
                print("\n⚠️  检测到键盘中断，正在保存数据...")
                self._save_unsaved_results()
            raise
        except Exception as e:
            # 捕获其他异常，尝试保存数据
            print(f"\n❌ 发生异常: {e}")
            print("正在尝试保存已处理的数据...")
            self._save_unsaved_results()
            raise
        
        # 5. 重试错误样本（只调用之前出错的模型）
        retry_results: List[Dict] = []
        try:
            if error_results and not self._shutdown_requested:
                print("\n🔄 重试错误样本...")
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    future_to_item = {executor.submit(self.evaluate_item, item, True): item for item in error_results}
                    
                    pbar = tqdm(total=len(error_results), desc="Retry Errors", unit="q") if tqdm else None
                    
                    retry_completed = 0
                    for future in as_completed(future_to_item):
                        # 检查是否请求关闭
                        if self._shutdown_requested:
                            print("\n⚠️  检测到关闭请求，正在停止重试任务...")
                            for f in future_to_item:
                                f.cancel()
                            break
                        
                        res = future.result()
                        retry_results.append(res)
                        # 同步更新实例变量
                        self._retry_results_for_save = retry_results
                        
                        retry_completed += 1
                        
                        # 根据输出格式选择保存方式
                        if self._output_format == "jsonl":
                            # JSONL 格式：实时写入
                            self._write_jsonl_item(res)
                            res_id = str(res.get("id", ""))
                            if res_id:
                                saved_result_ids.add(res_id)
                        else:
                            # JSON 格式：加入 buffer
                            with self._buffer_lock:
                                self._result_buffer.append(res)
                                # 当 buffer 达到 batch_size 时，批量写入
                                if len(self._result_buffer) >= self.batch_size:
                                    self._flush_buffer()
                        
                        # JSON 格式的批量保存检查点
                        if self._output_format == "json" and retry_completed % self.batch_size == 0:
                            final_results.extend(retry_results)
                            save_checkpoint()
                            # 清空已保存的重试结果，避免重复
                            retry_results = []
                            self._retry_results_for_save = []
                        
                        if pbar: pbar.update(1)
                    
                    # 重试完成后，保存剩余的重试结果
                    if self._output_format == "json":
                        # JSON 格式：刷新 buffer 和保存检查点
                        self._flush_buffer()
                        if retry_results:
                            final_results.extend(retry_results)
                            save_checkpoint()
                            retry_results = []
                            self._retry_results_for_save = []
                    # JSONL 格式：已经实时写入，无需额外保存
                    
                    if pbar: pbar.close()
        except KeyboardInterrupt:
            if not self._shutdown_requested:
                print("\n⚠️  检测到键盘中断，正在保存数据...")
                self._save_unsaved_results()
            raise
        except Exception as e:
            print(f"\n❌ 重试过程中发生异常: {e}")
            print("正在尝试保存已处理的数据...")
            self._save_unsaved_results()
            raise
        finally:
            # 恢复原始信号处理器
            signal.signal(signal.SIGINT, original_sigint)
            signal.signal(signal.SIGTERM, original_sigterm)
        
        # 如果被中断，直接返回（数据已在信号处理器中保存）
        if self._shutdown_requested:
            return
        
        # 6. 清理error文件中已成功重试的记录
        if retry_results:
            self._cleanup_successful_retries_from_error_file(out_dir, retry_results)
        
        # 合并所有结果：历史正常结果 + 新处理结果 + 重试结果
        all_results = existing_results + final_results + retry_results

        # 不再输出主结果 JSON，仅输出按等级划分的文件夹
        print(f"\n✅ 处理完成！结果已输出到文件夹: {os.path.abspath(out_dir)}")
        
        # 打印并记录统计信息
        stats_text = self._print_stats(all_results, return_text=True)
        from module2.logger import log_stats
        log_stats(stats_text)
        
        # 在单独的文件夹中输出 L1-L4 & 汇总文件（全量：历史 + 新增）
        self._save_by_level_and_summary(all_results, out_dir)
        
        # 记录输出文件信息到日志
        from module2.logger import log_output_info
        log_output_info(out_dir)
        
        # 关闭日志文件
        close_log_file()

    def _print_stats(self, results: List[Dict], return_text: bool = False):
        """
        打印统计摘要
        
        Args:
            results: 结果列表
            return_text: 是否返回文本（用于写入日志）
        
        Returns:
            如果 return_text=True，返回统计文本；否则返回 None
        """
        # 分离正常结果和错误结果
        normal_results = [r for r in results if "model_error" not in r and "error" not in r]
        error_results = [r for r in results if "model_error" in r or "error" in r]
        
        # 打印分隔线（控制台输出）
        if not return_text:
            print("\n" + "=" * 30 + " 评估统计 " + "=" * 30)
        
        # 构建统计文本
        stats_lines = []
        stats_lines.append(f"总样本数: {len(results)}")
        stats_lines.append(f"  - 正常处理: {len(normal_results)} ({len(normal_results)/len(results)*100:.1f}%)")
        if error_results:
            stats_lines.append(f"  - 模型错误: {len(error_results)} ({len(error_results)/len(results)*100:.1f}%)")
        stats_lines.append("")
        
        # 使用正常结果进行后续统计
        valid = normal_results

        # ---------------- 全局匹配率（按模型） ----------------
        for m in MODEL_KEYS:
            enabled_count = sum(1 for r in valid if r.get(m, {}).get("enabled"))
            match_count = sum(1 for r in valid if r.get(m, {}).get("enabled") and r.get(m, {}).get("match_gt"))
            if enabled_count > 0:
                line = f"[{m}] 准确率: {match_count}/{enabled_count} ({match_count/enabled_count*100:.1f}%)"
                stats_lines.append(line)
                print(line)

        # ---------------- 按题型统计正确率 ----------------
        stats_lines.append("")
        stats_lines.append("按 question_type 统计正确率（基于裁判结果 match_gt）:")
        print("\n按 question_type 统计正确率（基于裁判结果 match_gt）:")
        qt_stats = self._calculate_stats_by_field(valid, "question_type")
        for qtype, models in qt_stats.items():
            stats_lines.append(f"  题型 {qtype}:")
            print(f"  题型 {qtype}:")
            for m, (enabled_cnt, match_cnt) in models.items():
                acc = match_cnt / enabled_cnt * 100 if enabled_cnt > 0 else 0.0
                line = f"    - {m}: {match_cnt}/{enabled_cnt} ({acc:.1f}%)"
                stats_lines.append(line)
                print(line)

        # ---------------- 按图片类型统计正确率 ----------------
        stats_lines.append("")
        stats_lines.append("按 image_type 统计正确率:")
        print("\n按 image_type 统计正确率:")
        img_stats = self._calculate_stats_by_field(valid, "image_type")
        for itype, models in img_stats.items():
            stats_lines.append(f"  图片类型 {itype}:")
            print(f"  图片类型 {itype}:")
            for m, (enabled_cnt, match_cnt) in models.items():
                acc = match_cnt / enabled_cnt * 100 if enabled_cnt > 0 else 0.0
                line = f"    - {m}: {match_cnt}/{enabled_cnt} ({acc:.1f}%)"
                stats_lines.append(line)
                print(line)
        
        # ---------------- 难度分布 ----------------
        levels = {}
        for r in valid:
            lvl = r.get("classification", {}).get("level", "Unknown")
            levels[lvl] = levels.get(lvl, 0) + 1
        
        stats_lines.append("")
        stats_lines.append("难度分布（L1-L4）:")
        print("\n难度分布（L1-L4）:")
        for l in DIFFICULTY_LEVELS:
            count = levels.get(l, 0)
            if count > 0:
                line = f"  {l}: {count} ({count/len(valid)*100:.1f}%)"
                stats_lines.append(line)
                print(line)
        
        # 打印结束分隔线（控制台输出）
        if not return_text:
            print("=" * 70)
        
        if return_text:
            return "\n".join(stats_lines)
    
    def _calculate_stats_by_field(self, valid_results: List[Dict], field_name: str) -> Dict:
        """
        按指定字段统计模型正确率（通用方法，用于按题型、图片类型等统计）
        
        Args:
            valid_results: 有效结果列表
            field_name: 字段名（如 "question_type", "image_type"）
        
        Returns:
            {字段值: {模型键: [enabled_count, match_count]}}
        """
        stats = {}
        for r in valid_results:
            field_value = r.get(field_name, "Unknown")
            bucket = stats.setdefault(field_value, {})
            for m in MODEL_KEYS:
                mdata = r.get(m, {})
                if not mdata.get("enabled"):
                    continue
                model_bucket = bucket.setdefault(m, [0, 0])
                model_bucket[0] += 1
                if mdata.get("match_gt"):
                    model_bucket[1] += 1
        return stats

    def _cleanup_successful_retries_from_error_file(self, output_dir: str, retry_results: List[Dict]):
        """
        清理error文件中已成功重试的记录
        
        Args:
            output_dir: 输出目录
            retry_results: 重试结果列表
        """
        # 找出成功处理的重试结果（不再有model_error或error标记）
        successful_retry_ids = set()
        for res in retry_results:
            res_id = str(res.get("id", ""))
            if res_id and "model_error" not in res and "error" not in res:
                successful_retry_ids.add(res_id)
        
        if not successful_retry_ids:
            return
        
        # 确定error文件路径
        file_ext = ".jsonl" if self._output_format == "jsonl" else ".json"
        error_path = os.path.join(output_dir, f"error{file_ext}")
        
        if not os.path.isfile(error_path):
            return
        
        try:
            if self._output_format == "jsonl":
                # JSONL 格式：逐行读取，过滤掉已成功处理的记录
                remaining_errors = []
                with open(error_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            item = json.loads(line)
                            item_id = str(item.get("id", ""))
                            # 如果这个ID不在成功重试列表中，保留它
                            if item_id not in successful_retry_ids:
                                remaining_errors.append(line)
                        except json.JSONDecodeError:
                            # 如果解析失败，保留原行（可能是格式问题，但保留更安全）
                            remaining_errors.append(line)
                
                # 重新写入error文件
                with open(error_path, "w", encoding="utf-8") as f:
                    for line in remaining_errors:
                        f.write(line + "\n")
                
                removed_count = len(successful_retry_ids)
                remaining_count = len(remaining_errors)
                if removed_count > 0:
                    print(f"🧹 已从error文件中删除 {removed_count} 条成功重试的记录，剩余 {remaining_count} 条错误记录")
            else:
                # JSON 格式：读取、过滤、保存
                existing_errors = []
                try:
                    data = load_json(error_path)
                    if isinstance(data, list):
                        existing_errors = data
                except Exception:
                    existing_errors = []
                
                # 过滤掉已成功处理的记录
                remaining_errors = []
                for item in existing_errors:
                    item_id = str(item.get("id", ""))
                    if item_id not in successful_retry_ids:
                        remaining_errors.append(item)
                
                # 保存更新后的error文件
                save_json(remaining_errors, error_path)
                
                removed_count = len(successful_retry_ids)
                remaining_count = len(remaining_errors)
                if removed_count > 0:
                    print(f"🧹 已从error文件中删除 {removed_count} 条成功重试的记录，剩余 {remaining_count} 条错误记录")
        except Exception as e:
            print(f"⚠️ 清理error文件失败: {e}")
            if self.debug_mode:
                import traceback
                traceback.print_exc()

    def _save_by_level_and_summary(self, results: List[Dict], output_dir: str):
        """
        输出结构：
        - 一个文件夹，包含：
          - L1.json/jsonl ~ L4.json/jsonl：不同难度级别的问题结果（完整 item 列表）
          - error.json/jsonl：模型生成出错的题目（不包含在 L1-L4 中）
          - summary.json：统计当前（以及历史追加）分类情况
        """
        from collections import defaultdict

        # 1）准备目录
        ensure_dir(output_dir)

        # 2）分离正常结果和错误结果
        normal_results: List[Dict] = []
        error_results: List[Dict] = []
        
        for item in results:
            # 检查是否有模型错误或其他错误
            if "model_error" in item or "error" in item:
                error_results.append(item)
            else:
                normal_results.append(item)
        
        # 3）保存错误结果到 error.json/jsonl
        if error_results:
            file_ext = ".jsonl" if self._output_format == "jsonl" else ".json"
            error_path = os.path.join(output_dir, f"error{file_ext}")
            try:
                if self._output_format == "jsonl":
                    # JSONL 格式：逐行写入
                    with open(error_path, "w", encoding="utf-8") as f:
                        for item in error_results:
                            f.write(json.dumps(item, ensure_ascii=False) + "\n")
                else:
                    # JSON 格式：标准保存
                    save_json(error_results, error_path)
                print(f"⚠️  已输出错误样本 {len(error_results)} 条 -> {error_path}")
            except Exception as e:
                print(f"❌ 保存 error{file_ext} 失败: {e}")

        # 4）按 level 拆分正常结果到 L1-L4（不再有 L0）
        level_buckets: Dict[str, List[Dict]] = defaultdict(list)
        for item in normal_results:
            level = item.get("classification", {}).get("level", "Unknown")
            # 如果遇到 L0 或 Unknown，统一归类到 L4
            if level not in DIFFICULTY_LEVELS:
                level = "L4"
            level_buckets[level].append(item)

        # 根据输出格式选择文件扩展名
        file_ext = ".jsonl" if self._output_format == "jsonl" else ".json"
        
        for lvl in DIFFICULTY_LEVELS:
            items = level_buckets.get(lvl, [])
            out_path = os.path.join(output_dir, f"{lvl}{file_ext}")
            try:
                if self._output_format == "jsonl":
                    # JSONL 格式：逐行写入
                    with open(out_path, "w", encoding="utf-8") as f:
                        for item in items:
                            f.write(json.dumps(item, ensure_ascii=False) + "\n")
                else:
                    # JSON 格式：标准保存
                    save_json(items, out_path)
                print(f"💾 已输出 {lvl} 级样本 {len(items)} 条 -> {out_path}")
            except Exception as e:
                print(f"❌ 保存 {lvl} 文件失败: {e}")

        # 5）生成/更新 summary.json（仅统计正常结果）
        #    - 对于断点续传：normal_results 已经包含历史 + 新增数据，这里直接"全量重算"一次统计即可
        #    - 对于重新评估（re_evaluate）：由外层指定全新的输出目录，这里始终基于当前 normal_results 全量重算
        summary_path = os.path.join(output_dir, "summary.json")

        # 当前这一次运行的统计
        current_summary = {
            "total_items": len(normal_results),
            "error_items": len(error_results),
            "levels": {},
            "by_question_type": {},
            "by_image_type": {},
            "models": {key: {"enabled": 0, "correct": 0} for key in MODEL_KEYS},
            # 这里的 runs 代表"基于当前 results 全量重算的版本号"，
            # 目前简单处理为：如果存在旧 summary，则在其基础上 +1，否则为 1
            "runs": 1
        }

        # 级别统计（不再有 L0）
        for lvl in DIFFICULTY_LEVELS:
            current_summary["levels"][lvl] = len(level_buckets.get(lvl, []))

        # 按题型 & 难度统计
        for item in normal_results:
            qtype = item.get("question_type", "Unknown")
            lvl = item.get("classification", {}).get("level", "Unknown")
            qt_bucket = current_summary["by_question_type"].setdefault(qtype, {})
            qt_bucket[lvl] = qt_bucket.get(lvl, 0) + 1

            itype = item.get("image_type", "Unknown")
            it_bucket = current_summary["by_image_type"].setdefault(itype, {})
            it_bucket[lvl] = it_bucket.get(lvl, 0) + 1

            for m in MODEL_KEYS:
                mdata = item.get(m, {})
                if not mdata.get("enabled"):
                    continue
                current_summary["models"][m]["enabled"] += 1
                if mdata.get("match_gt"):
                    current_summary["models"][m]["correct"] += 1

        # 如果已有 summary.json，则仅更新 runs（表示重新计算过多少次），
        # 其它统计全部以 current_summary 为准（避免断点续传时重复累加）
        if os.path.exists(summary_path):
            try:
                old = load_json(summary_path)
                if isinstance(old, dict):
                    current_summary["runs"] = old.get("runs", 0) + 1
            except Exception as e:
                print(f"⚠️ 读取旧的 summary.json 失败，将仅保存本次统计: {e}")

        try:
            save_json(current_summary, summary_path)
            print(f"📊 已更新汇总统计 -> {summary_path}")
        except Exception as e:
            print(f"❌ 保存 summary.json 失败: {e}")


    def _get_versioned_output_file(self, base_output_file: str) -> str:
        """
        生成带版本号的输出文件名
        
        注意：此方法目前不再使用，版本号管理已移至 shell 脚本（main.sh）。
        保留此方法以防将来需要。
        
        例如：
        - module2_result.json -> module2_result_v2.json
        - module2_result_v2.json -> module2_result_v3.json
        
        Args:
            base_output_file: 基础输出文件路径
            
        Returns:
            带版本号的文件路径
        """
        # 分离目录、文件名和扩展名
        output_dir = os.path.dirname(base_output_file)
        base_name = os.path.basename(base_output_file)
        
        # 分离文件名和扩展名
        if '.' in base_name:
            name_part, ext = os.path.splitext(base_name)
        else:
            name_part = base_name
            ext = ""
        
        # 检查是否已有版本号（格式：name_v2.ext）
        version_pattern = r'_v(\d+)$'
        match = re.search(version_pattern, name_part)
        
        if match:
            # 已有版本号，提取并加1
            current_version = int(match.group(1))
            base_name_part = name_part[:match.start()]
            next_version = current_version + 1
        else:
            # 没有版本号，查找目录中是否有同名文件的不同版本
            base_name_part = name_part
            current_version = 0
            
            # 查找目录中所有同名文件的不同版本
            if output_dir and os.path.exists(output_dir):
                pattern = re.compile(rf'^{re.escape(name_part)}_v(\d+){re.escape(ext)}$')
                for filename in os.listdir(output_dir):
                    match = pattern.match(filename)
                    if match:
                        version = int(match.group(1))
                        if version > current_version:
                            current_version = version
            
            next_version = current_version + 1
        
        # 生成新版本文件名
        new_name = f"{base_name_part}_v{next_version}{ext}"
        return os.path.join(output_dir, new_name) if output_dir else new_name

def main():
    parser = argparse.ArgumentParser(description="模块2：模型评估")
    parser.add_argument("--input", type=str, help="输入文件路径（支持 .json 和 .jsonl 格式）")
    parser.add_argument("--output", type=str, help="输出目录路径（文件夹路径，不需要文件名）")
    parser.add_argument("--output-format", type=str, default="json", choices=["json", "jsonl"],
                       help="输出格式：json 或 jsonl（默认：json）")
    parser.add_argument("-re", "--re", action="store_true", 
                       help="重新评估模式：跳过断点续传，始终对输入文件中的所有样本重新评估（不复用已有结果）")
    parser.add_argument("--workers", type=int, default=None,
                       help="并发线程数（覆盖默认值）")
    parser.add_argument("--batch", type=int, default=None,
                       help="批量保存大小（覆盖默认值）")
    parser.add_argument("--debug", action="store_true",
                       help="启用调试模式（打印 traceback、judge_reasoning 等）")
    
    args = parser.parse_args()
    
    evaluator = Module2ModelEvaluation(
        max_workers=args.workers,
        batch_size=args.batch,
        debug_mode=args.debug,
    )
    evaluator.batch_evaluate(
        input_file=args.input, 
        output_dir=args.output, 
        output_format=args.output_format,
        re_evaluate=args.re
    )

if __name__ == "__main__":
    main()