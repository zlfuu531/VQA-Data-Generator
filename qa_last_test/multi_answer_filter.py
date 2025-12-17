"""
多次回答筛题脚本

功能：
- 对输入评测集中的每个题目，用同一个模型回答 N 次
- 每次回答都用裁判模型判定对错
- 统计「回答正确次数」
- 将：
  - 正确次数 <= 阈值 a 的题目  -> 输出到一个文件（困难题 / 不稳定题）
  - 正确次数  > 阈值 a 的题目 -> 输出到另一个文件

实现思路：
- 复用 evaluate 模块里的：
  - data_loader.load_and_validate       （加载标准化后的题目）
  - main.evaluate_single_item           （完整的一次评测逻辑：构造 prompt、调模型、裁判判分、多轮题支持等）
"""

import os
import sys
import json
import argparse
import logging
import random
import re
from datetime import datetime
from typing import Any, Dict, List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVAL_DIR = os.path.join(PROJECT_ROOT, "evaluate")

# 确保可以 import evaluate 目录下的模块
if EVAL_DIR not in sys.path:
    sys.path.insert(0, EVAL_DIR)

try:
    # 与 evaluate/main.py 一致的导入方式
    from data_loader import load_and_validate  # type: ignore
    import config as eval_config  # type: ignore
    import main as eval_main  # type: ignore
except ImportError as e:  # pragma: no cover - 环境导入错误直接抛出
    raise ImportError(f"无法导入 evaluate 模块，请确认目录结构。原始错误: {e}")

# 导入详细日志模块
from logger import (
    init_log_file,
    log_question_start,
    log_run_attempt,
    log_single_round_response,
    log_single_round_response_simple,
    log_question_summary,
    log_stats,
    close_log_file
)


def _strip_boxed_content(text: str) -> str:
    """移除文本中的 \\boxed{...} 片段，只保留思考/分析部分。"""
    if not text:
        return ""
    # 粗略移除所有 \\boxed{...}，只用于过程展示
    cleaned = re.sub(r"\\\\boxed\{.*?\}", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"\\boxed\{.*?\}", "", cleaned, flags=re.DOTALL)
    return cleaned.strip()


def _build_process_from_round_data(round_data: Dict[str, Any]) -> str:
    """
    从单轮数据构造 process（用于多轮题目的每一轮）：
    - 从 round_data 的 raw_response 提取思考内容 + model_answer
    """
    round_model_answer = round_data.get("model_answer", "") or ""
    round_non_box_text = _strip_boxed_content(round_model_answer)
    
    round_reasoning_text = ""
    round_raw_response = round_data.get("raw_response")
    try:
        if isinstance(round_raw_response, dict):
            choices = round_raw_response.get("choices") or []
            if choices:
                msg = choices[0].get("message") or {}
                # 按优先级提取思考内容：reasoning > reasoning_content > reasoning_details
                # 只保留优先级最高的一个，避免冗余
                r = msg.get("reasoning")
                if isinstance(r, str) and r.strip():
                    round_reasoning_text = r.strip()
                else:
                    rc = msg.get("reasoning_content")
                    if isinstance(rc, str) and rc.strip():
                        round_reasoning_text = rc.strip()
                    else:
                        rd = msg.get("reasoning_details")
                        if isinstance(rd, list):
                            texts: List[str] = []
                            for d in rd:
                                if isinstance(d, dict):
                                    t = d.get("text")
                                    if isinstance(t, str) and t.strip():
                                        texts.append(t.strip())
                                elif isinstance(d, str) and d.strip():
                                    texts.append(d.strip())
                            if texts:
                                round_reasoning_text = "\n\n".join(texts)
                        elif isinstance(rd, str) and rd.strip():
                            round_reasoning_text = rd.strip()
    except Exception:
        round_reasoning_text = ""
    
    parts: List[str] = []
    if round_reasoning_text:
        parts.append(f"【思考】\n{round_reasoning_text}")
    if round_non_box_text:
        parts.append(f"【回答】\n{round_non_box_text}")
    
    if parts:
        return "\n\n".join(parts)
    return round_model_answer


def _build_process_from_model_data(model_data: Dict[str, Any]) -> str:
    """
    从 evaluate.single_item 的 model_data 中构造本次 run 的 process：
    - 单轮题目：从 model_data 的 raw_response 提取思考内容 + model_answer
    - 注意：多轮题目不应该调用这个函数，应该在 process_single_item 中按轮次处理
    """
    model_answer = model_data.get("model_answer", "") or ""
    base_text = model_answer
    non_box_text = _strip_boxed_content(base_text)

    reasoning_text = ""
    raw_response = model_data.get("raw_response")
    try:
        if isinstance(raw_response, dict):
            choices = raw_response.get("choices") or []
            if choices:
                msg = choices[0].get("message") or {}
                # 按优先级提取思考内容：reasoning > reasoning_content > reasoning_details
                # 只保留优先级最高的一个，避免冗余
                r = msg.get("reasoning")
                if isinstance(r, str) and r.strip():
                    reasoning_text = r.strip()
                else:
                    rc = msg.get("reasoning_content")
                    if isinstance(rc, str) and rc.strip():
                        reasoning_text = rc.strip()
                    else:
                        rd = msg.get("reasoning_details")
                        if isinstance(rd, list):
                            texts: List[str] = []
                            for d in rd:
                                if isinstance(d, dict):
                                    t = d.get("text")
                                    if isinstance(t, str) and t.strip():
                                        texts.append(t.strip())
                                elif isinstance(d, str) and d.strip():
                                    texts.append(d.strip())
                            if texts:
                                reasoning_text = "\n\n".join(texts)
                        elif isinstance(rd, str) and rd.strip():
                            reasoning_text = rd.strip()
    except Exception:
        reasoning_text = ""

    parts: List[str] = []
    if reasoning_text:
        parts.append(f"【思考】\n{reasoning_text}")
    if non_box_text:
        parts.append(f"【回答】\n{non_box_text}")

    if parts:
        return "\n\n".join(parts)
    return base_text


def run_single_attempt(
    item: Dict[str, Any],
    model_name: str,
    profile: str,
) -> Tuple[Dict[str, Any], Dict[str, Any], bool]:
    """对单个题目执行一次完整评测（单模型 + 单画像），复用 evaluate_single_item。

    Returns:
        (full_result, model_data, is_correct)
        - full_result: evaluate_single_item 返回的完整结果结构
        - model_data: 该模型在该画像下的一次评测数据字典
        - is_correct: 这一次是否判定为正确（单轮或多轮已聚合）
    """
    # enabled_models / profiles 都只传一个
    full_result = eval_main.evaluate_single_item(
        item,
        enabled_models=[model_name],
        profiles=[profile],
        workers=1,
    )

    if not full_result or not isinstance(full_result, dict):
        # evaluate_single_item 在异常时会返回 {"question_id": ..., "error": ...}
        # 这种情况统一视为「本次不算正确」
        return full_result or {"question_id": item.get("question_id")}, {}, False

    profiles_data = full_result.get("profiles", {})
    profile_data = profiles_data.get(profile, {})
    models_data = profile_data.get("models", {})
    model_data = models_data.get(model_name, {})

    # 兜底：如果结构缺失，也视为错误
    if not model_data:
        return full_result, {}, False

    is_multi_round = full_result.get("is_multi_round", model_data.get("is_multi_round", False))

    # 判断逻辑：
    # - 多轮题：需要每轮都正确才算正确（使用 all_rounds_correct 或 is_correct）
    # - 单轮题：一次正确就算正确（使用 is_correct）
    is_correct = False
    if is_multi_round:
        # 多轮题：优先用 is_correct（如果 evaluate 模块已聚合），其次用 all_rounds_correct
        if "is_correct" in model_data:
            is_correct = bool(model_data["is_correct"])
        elif "all_rounds_correct" in model_data:
            is_correct = bool(model_data["all_rounds_correct"])
    else:
        # 单轮题：直接用 is_correct
        is_correct = bool(model_data.get("is_correct", False))

    return full_result, model_data, is_correct


def build_output_item(
    base_item: Dict[str, Any],
    profile: str,
    model_name: str,
    n_runs: int,
    correct_count: int,
    run_details: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """构造输出文件中的单条记录结构。"""
    question_id = (
        base_item.get("question_id")
        or base_item.get("id")
        or base_item.get("image_id")
        or ""
    )

    out: Dict[str, Any] = {
        "question_id": question_id,
        "image_id": base_item.get("image_id", ""),
        "image_path": base_item.get("image_path", ""),
        "image_type": base_item.get("image_type", ""),
        "question_type": base_item.get("question_type", ""),
        "question": base_item.get("question", ""),
        "answer": base_item.get("answer", ""),
        "options": base_item.get("options", None),
        "profile": profile,
        "model_name": model_name,
        "n_runs": n_runs,
        "correct_count": correct_count,
        # 每次评测的详细信息：包括 process / answer / match_gt / judge_reasoning 等
        "runs": run_details,
    }

    # 额外保留部分分类字段，便于后续统计
    for field in ["scenario", "capability", "difficulty", "source"]:
        if field in base_item:
            out[field] = base_item[field]

    return out


def main():
    parser = argparse.ArgumentParser(
        description="对评测集每道题用同一模型回答 N 次，并按正确次数分桶输出"
    )
    parser.add_argument(
        "--input_file",
        type=str,
        required=True,
        help="输入评测集文件路径（支持 .json/.jsonl/.csv，与 evaluate 一致）",
    )
    parser.add_argument(
        "--model",
        type=str,
        required=True,
        help="评测使用的模型名称（需在 evaluate/config.py 的 MODEL_DEFINITIONS / API_CONFIG 中配置）",
    )
    parser.add_argument(
        "--profile",
        type=str,
        default="expert",
        help="用户画像（beginner/retail/expert/expert_cot），默认 expert",
    )
    parser.add_argument(
        "--n_runs",
        type=int,
        default=3,
        help="每道题重复回答次数 N，默认 3",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=1,
        help="阈值 a：正确次数 <= a 的题目放入 hard_output，其余放入 other_output，默认 1",
    )
    parser.add_argument(
        "--hard_output",
        type=str,
        required=True,
        help="输出文件：正确次数 <= a 的题目及其多次回答结果",
    )
    parser.add_argument(
        "--other_output",
        type=str,
        required=True,
        help="输出文件：正确次数 > a 的题目及其多次回答结果",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="并行处理的题目数量（默认1，串行处理）。注意：每道题的多次回答仍然是串行的",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="限制处理的题目数量：0 或不填表示处理全部，大于0时只处理前 N 条（或随机抽样 N 条）",
    )
    parser.add_argument(
        "--use_random",
        action="store_true",
        help="是否在抽样前先随机打乱题目顺序（与 --limit 配合使用）。默认 False 表示按原顺序取前 N 条",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="随机种子（仅当 --use_random 且 --limit>0 时有效）",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="是否开启断点续跑：如果 hard/other 输出文件已存在，将加载已完成题目并跳过，仅补充未完成部分",
    )
    parser.add_argument(
        "--log_dir",
        type=str,
        default="",
        help="日志目录（默认：当前脚本目录下的 logs 子目录）",
    )
    parser.add_argument(
        "--log_level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="日志级别（DEBUG/INFO/WARNING/ERROR），默认 INFO",
    )
    parser.add_argument(
        "--batch_size",
        type=int,
        default=10,
        help="批量写入大小（默认10，每处理N条题目后保存一次结果）",
    )
    parser.add_argument(
        "--log_mode",
        type=str,
        default="detailed",
        choices=["simple", "detailed"],
        help="日志模式：simple(简化) 或 detailed(详细)，默认 detailed",
    )

    args = parser.parse_args()

    # 日志配置：根据 log_mode 决定保存哪种日志
    script_dir = os.path.dirname(os.path.abspath(__file__))
    log_dir = args.log_dir or os.path.join(script_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # 设置日志级别
    log_level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
    }
    log_level = log_level_map.get(args.log_level.upper(), logging.INFO)

    logger = logging.getLogger()
    logger.setLevel(log_level)
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    # 控制台输出始终开启
    ch = logging.StreamHandler()
    ch.setLevel(log_level)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # 根据 log_mode 决定是否创建文件日志
    if args.log_mode == "detailed":
        # detailed 模式：只创建详细日志文件，不创建基本日志文件
        detailed_log_path = init_log_file(
            log_dir=log_dir,
            input_file=args.input_file,
            model_name=args.model,
            profile=args.profile,
            n_runs=args.n_runs,
            threshold=args.threshold,
            workers=args.workers,
            hard_output=args.hard_output,
            other_output=args.other_output,
            log_mode=args.log_mode
        )
        logging.info(f"详细日志写入文件: {detailed_log_path} (模式: {args.log_mode})")
    else:
        # simple 模式：只创建基本日志文件，不创建详细日志文件
        log_file = os.path.join(log_dir, f"multi_answer_filter_{timestamp}.log")
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(log_level)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
        logging.info(f"日志写入文件: {log_file} (模式: {args.log_mode})")
        logging.info(f"日志级别: {args.log_level}")

    # 简单检查模型是否在配置中
    if args.model not in eval_config.API_CONFIG:
        raise ValueError(
            f"模型 '{args.model}' 不在 evaluate/config.py 的 API_CONFIG 中，请先在那里配置。"
        )

    logging.info(f"加载评测集: {args.input_file}")
    items = load_and_validate(args.input_file)
    total_count = len(items)
    logging.info(f"成功加载 {total_count} 条数据")

    # 处理 LIMIT / USE_RANDOM / SEED 抽样逻辑
    if args.limit and args.limit > 0 and total_count > 0:
        limit_n = min(args.limit, total_count)
        if args.use_random:
            rnd = random.Random(args.seed)
            rnd.shuffle(items)
            items = items[:limit_n]
            logging.info(
                f"启用随机抽样: use_random=True, seed={args.seed}, "
                f"原始 {total_count} 条，本次随机抽取 {len(items)} 条"
            )
        else:
            items = items[:limit_n]
            logging.info(
                f"按顺序截取前 {len(items)} 条数据进行处理（总共 {total_count} 条，limit={args.limit}）"
            )
    else:
        logging.info(
            f"未设置 limit 或 limit<=0，本次处理全部 {total_count} 条数据 "
            f"(use_random={args.use_random}, seed={args.seed})"
        )

    # 断点续跑：如果开启，则从已有输出文件中恢复已完成题目
    processed_ids = set()

    def _extract_qid(item: Dict[str, Any]) -> str:
        return (
            item.get("question_id")
            or item.get("id")
            or item.get("image_id")
            or ""
        )

    hard_items: List[Dict[str, Any]] = []
    other_items: List[Dict[str, Any]] = []

    if args.resume:
        # 续跑模式：从 hard_output 和 other_output 两个文件中读取已完成的 question_id
        # 这两个文件中的 question_id 都会被收集到 processed_ids 集合中
        # 后续处理时会跳过这些已完成的题目
        def _load_existing(path: str) -> List[Dict[str, Any]]:
            if not os.path.exists(path):
                return []
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, list):
                    logging.warning(f"断点续跑：文件 {path} 内容不是列表，忽略。")
                    return []
                for it in data:
                    if isinstance(it, dict):
                        qid = _extract_qid(it)
                        if qid:
                            processed_ids.add(qid)
                return data
            except Exception as e:
                logging.warning(f"断点续跑：读取历史文件 {path} 失败，将忽略此文件。错误: {e}")
                return []

        hard_items = _load_existing(args.hard_output)
        other_items = _load_existing(args.other_output)

        logging.info(
            f"断点续跑开启：已从历史结果中加载 "
            f"hard_items={len(hard_items)}, other_items={len(other_items)}, "
            f"已完成题目数（去重）={len(processed_ids)}"
        )
        logging.info(
            f"续跑检测：从 {args.hard_output} 和 {args.other_output} 两个文件中提取 question_id，"
            f"已收集 {len(processed_ids)} 个已完成的题目ID"
        )
    else:
        logging.info("未开启断点续跑，将重新处理所有题目。")

    # 根据是否已处理过滤待处理题目列表
    indexed_items: List[Tuple[int, Dict[str, Any]]] = []
    for idx, item in enumerate(items, 1):
        qid = _extract_qid(item) or f"idx_{idx}"
        if qid in processed_ids:
            logging.info(f"跳过已完成题目 idx={idx}, question_id={qid}")
            continue
        indexed_items.append((idx, item))

    # 辅助函数定义
    def _safe_mkdir(path: str) -> None:
        dir_path = os.path.dirname(os.path.abspath(path))
        if dir_path and not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)

    def _save_results_batch(items: List[Dict[str, Any]], output_path: str, is_final: bool = False):
        """批量保存结果到文件
        
        注意：在续跑模式下，需要读取文件中的已有数据，然后合并新数据
        确保不会覆盖已有数据，也不会重复保存
        """
        _safe_mkdir(output_path)
        try:
            # 始终读取文件中的已有数据（如果文件存在）
            existing_items = []
            existing_ids = set()
            if os.path.exists(output_path):
                try:
                    with open(output_path, "r", encoding="utf-8") as f:
                        existing_data = json.load(f)
                        if isinstance(existing_data, list):
                            existing_items = existing_data
                            existing_ids = {item.get("question_id", "") for item in existing_items if item.get("question_id")}
                except Exception as e:
                    logging.warning(f"读取已有文件失败: {e}，将创建新文件")
            
            # 使用字典来存储，以 question_id 为 key
            # 先添加已有数据
            items_dict = {}
            for item in existing_items:
                # 使用 _extract_qid 函数提取ID，确保兼容多种ID字段
                item_id = _extract_qid(item)
                if item_id:  # 只保存有有效ID的项
                    items_dict[item_id] = item
            
            # 添加新处理的数据（会更新相同 question_id 的数据）
            new_count = 0
            for item in items:
                item_id = _extract_qid(item)
                if item_id:  # 只保存有有效ID的项
                    if item_id not in items_dict:
                        new_count += 1
                    items_dict[item_id] = item
                else:
                    # 如果没有有效ID，记录警告但仍然保存（使用临时ID）
                    logging.warning(f"保存结果时发现缺少有效ID的项，将使用临时ID: {item}")
                    temp_id = f"temp_{len(items_dict)}"
                    items_dict[temp_id] = item
                    new_count += 1
            
            # 转换为列表并保存
            all_items = list(items_dict.values())
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(all_items, f, ensure_ascii=False, indent=2)
            
            if new_count > 0 or is_final:
                logging.debug(f"批量保存 {new_count} 条新结果到 {output_path}（总计 {len(all_items)} 条）")
        except Exception as e:
            logging.error(f"批量保存失败 ({output_path}): {e}")

    if not indexed_items:
        logging.info("没有需要新增处理的题目（可能全部已在历史结果中完成）。")
        # 仍然写回一次文件，保证输出存在
        _safe_mkdir(args.hard_output)
        _safe_mkdir(args.other_output)

        _save_results_batch(hard_items, args.hard_output, is_final=True)
        _save_results_batch(other_items, args.other_output, is_final=True)

        logging.info(
            f"完成！正确次数 <= {args.threshold} 的题目 {len(hard_items)} 条，其他题目 {len(other_items)} 条。"
        )
        logging.info(f"hard_output:  {os.path.abspath(args.hard_output)}")
        logging.info(f"other_output: {os.path.abspath(args.other_output)}")
        
        # 记录统计信息并关闭详细日志文件
        stats_text = f"""处理完成！
正确次数 <= {args.threshold} 的题目（hard）: {len(hard_items)} 条
正确次数 > {args.threshold} 的题目（other）: {len(other_items)} 条
总计: {len(hard_items) + len(other_items)} 条
hard_output: {os.path.abspath(args.hard_output)}
other_output: {os.path.abspath(args.other_output)}
注意：所有题目已在历史结果中完成，本次无需新增处理。
"""
        if args.log_mode == "detailed":
            log_stats(stats_text)
            close_log_file()
        return

    def process_single_item(item: Dict[str, Any], idx: int) -> Dict[str, Any]:
        """处理单个题目：执行 N 次回答，统计正确次数，构造输出条目

        Returns:
            输出条目字典，包含 correct_count 和 runs 等信息
        """
        item_id = (
            item.get("question_id")
            or item.get("id")
            or item.get("image_id")
            or f"idx_{idx}"
        )
        logging.info(f"=== 处理题目 {idx}/{len(items)}: question_id={item_id} ===")

        # 判断是否为多轮题目
        is_multi_round = False
        question = item.get("question", "")
        answer = item.get("answer", "")
        if isinstance(question, dict) or isinstance(answer, dict):
            is_multi_round = True
        
        # 记录问题开始
        question_preview = str(question)[:200] if question else ""
        log_question_start(
            question_id=item_id,
            question_num=idx,
            total_questions=len(items),
            is_multi_round=is_multi_round,
            question_preview=question_preview
        )

        correct_count = 0
        run_details: List[Dict[str, Any]] = []

        last_full_result: Dict[str, Any] = item  # 兜底

        for run_idx in range(1, args.n_runs + 1):
            logging.info(f"  -> 第 {run_idx}/{args.n_runs} 次回答 (question_id={item_id})")
            try:
                full_result, model_data, is_correct = run_single_attempt(
                    item, args.model, args.profile
                )
                # full_result 可能为 {"question_id": ..., "error": ...}
                if isinstance(full_result, dict):
                    last_full_result = full_result
            except Exception as e:
                logging.error(f"  ⚠️ 第 {run_idx} 次评测失败 (question_id={item_id}): {e}")
                model_data = {"error": str(e)}
                is_correct = False

            # 记录本次回答尝试
            log_run_attempt(
                question_id=item_id,
                question_num=idx,
                run_index=run_idx,
                n_runs=args.n_runs,
                is_correct=is_correct
            )

            # 记录本次结果
            run_entry: Dict[str, Any] = {
                "run_index": run_idx,
            }
            if isinstance(model_data, dict):
                is_multi_round = model_data.get("is_multi_round", False)
                rounds = model_data.get("rounds", [])
                
                if is_multi_round and isinstance(rounds, list) and len(rounds) > 0:
                    # 多轮题目：将 rounds 列表转换为字典格式，参考单轮格式
                    # 格式：rounds: {round1: {...}, round2: {...}}
                    processed_rounds_dict: Dict[str, Dict[str, Any]] = {}
                    for round_idx, round_item in enumerate(rounds, 1):
                        processed_round = round_item.copy()
                        
                        # 先提取需要的信息（在移除 raw_response 之前）
                        raw_response = processed_round.get("raw_response")
                        judge_response = processed_round.get("judge_response")
                        round_key = processed_round.get("round", f"round{round_idx}")
                        round_prompt = processed_round.get("prompt", "")
                        round_model_answer = processed_round.get("model_answer", "")
                        round_extracted_answer = processed_round.get("extracted_answer", "")
                        round_is_correct = processed_round.get("is_correct", False)
                        round_judge_reasoning = processed_round.get("judge_reasoning", "")
                        
                        # 记录到详细日志（包含完整的 raw_response 和 judge_response）
                        log_single_round_response(
                            question_id=item_id,
                            question_num=idx,
                            run_index=run_idx,
                            round_key=round_key,
                            round_num=round_idx,
                            prompt=round_prompt,
                            raw_response=raw_response,
                            judge_response=judge_response,
                            model_answer=round_model_answer,
                            extracted_answer=round_extracted_answer,
                            is_correct=round_is_correct,
                            judge_reasoning=round_judge_reasoning
                        )
                        
                        # 为每轮构造独立的 process（使用原始的 round_item，因为它包含 raw_response）
                        round_process = _build_process_from_round_data(round_item)
                        if round_process:
                            processed_round["process"] = round_process
                        
                        # 从输出中移除 raw_response 和 judge_response（已记录到详细日志）
                        processed_round.pop("raw_response", None)
                        processed_round.pop("judge_response", None)
                        
                        # 移除 conversation_history 字段（太占篇幅）
                        processed_round.pop("conversation_history", None)
                        
                        # 移除 round 字段（因为已经作为字典的 key）
                        processed_round.pop("round", None)
                        
                        # 将 round 数据添加到字典中，key 为 round_key（如 "round1", "round2"）
                        processed_rounds_dict[round_key] = processed_round
                    
                    run_entry["rounds"] = processed_rounds_dict
                    # 保留多轮题目的其他字段
                    for key in [
                        "is_multi_round",
                        "all_rounds_correct",
                        "total_response_time",
                        "total_judge_time",
                    ]:
                        if key in model_data:
                            run_entry[key] = model_data[key]
                else:
                    # 单轮题目：提取字段并记录到详细日志
                    # 提取 raw_response 和 judge_response 并记录到详细日志（然后从输出中移除）
                    raw_response = model_data.get("raw_response")
                    judge_response = model_data.get("judge_response")
                    prompt = model_data.get("prompt", "")
                    model_answer = model_data.get("model_answer", "")
                    extracted_answer = model_data.get("extracted_answer", "")
                    judge_reasoning = model_data.get("judge_reasoning", "")
                    
                    # 记录到详细日志
                    log_single_round_response_simple(
                        question_id=item_id,
                        question_num=idx,
                        run_index=run_idx,
                        prompt=prompt,
                        raw_response=raw_response,
                        judge_response=judge_response,
                        model_answer=model_answer,
                        extracted_answer=extracted_answer,
                        is_correct=is_correct,
                        judge_reasoning=judge_reasoning
                    )
                    
                    # 单轮题目：复制字段到 run_entry（不包含 raw_response 和 judge_response）
                    for key in [
                        "prompt",
                        "model_answer",
                        "extracted_answer",
                        "answer_for_judge",
                        "is_correct",
                        "reasoning",
                        "response_time",
                        "judge_time",
                        "match_gt",
                        "judge_reasoning",
                    ]:
                        if key in model_data:
                            run_entry[key] = model_data[key]
                    # 额外：为本次 run 构造 process（模型思考 + 去掉 boxed 的正文）
                    process_text = _build_process_from_model_data(model_data)
                    if process_text:
                        run_entry["process"] = process_text
            else:
                run_entry["raw_model_data"] = model_data

            run_entry["is_correct"] = bool(is_correct)
            run_details.append(run_entry)

            if is_correct:
                correct_count += 1

        # 记录问题总结
        log_question_summary(
            question_id=item_id,
            question_num=idx,
            correct_count=correct_count,
            n_runs=args.n_runs,
            threshold=args.threshold
        )

        # 构造输出条目
        output_item = build_output_item(
            base_item=last_full_result if isinstance(last_full_result, dict) else item,
            profile=args.profile,
            model_name=args.model,
            n_runs=args.n_runs,
            correct_count=correct_count,
            run_details=run_details,
        )

        return output_item

    hard_items: List[Dict[str, Any]] = []
    other_items: List[Dict[str, Any]] = []

    # 批量写入配置
    batch_size = args.batch_size
    hard_batch_buffer = []
    other_batch_buffer = []
    processed_count = 0

    # 并行处理题目
    if args.workers > 1:
        logging.info(f"使用并行处理，workers={args.workers}")
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(process_single_item, item, idx): (idx, item)
                for idx, item in indexed_items
            }

            for future in tqdm(as_completed(futures), total=len(indexed_items), desc="处理题目"):
                idx, item = futures[future]
                try:
                    output_item = future.result()
                    if output_item["correct_count"] <= args.threshold:
                        hard_items.append(output_item)
                        hard_batch_buffer.append(output_item)
                    else:
                        other_items.append(output_item)
                        other_batch_buffer.append(output_item)
                    
                    processed_count += 1
                    
                    # 批量保存
                    if processed_count % batch_size == 0:
                        if hard_batch_buffer:
                            _save_results_batch(hard_batch_buffer, args.hard_output, is_final=False)
                            hard_batch_buffer.clear()
                        if other_batch_buffer:
                            _save_results_batch(other_batch_buffer, args.other_output, is_final=False)
                            other_batch_buffer.clear()
                        logging.info(f"已处理 {processed_count}/{len(indexed_items)} 条题目，已批量保存")
                        
                except Exception as e:
                    item_id = item.get("question_id") or item.get("id") or f"idx_{idx}"
                    logging.error(f"处理题目 {item_id} 时出错: {e}", exc_info=True)
                    # 即使出错，也记录一个错误条目
                    error_item = build_output_item(
                        base_item=item,
                        profile=args.profile,
                        model_name=args.model,
                        n_runs=args.n_runs,
                        correct_count=0,
                        run_details=[{"run_index": 0, "error": str(e)}],
                    )
                    hard_items.append(error_item)
                    hard_batch_buffer.append(error_item)
                    processed_count += 1
                    
                    # 批量保存错误条目
                    if processed_count % batch_size == 0:
                        if hard_batch_buffer:
                            _save_results_batch(hard_batch_buffer, args.hard_output, is_final=False)
                            hard_batch_buffer.clear()
    else:
        # 串行处理（原有逻辑）
        logging.info("使用串行处理")
        for idx, item in indexed_items:
            try:
                output_item = process_single_item(item, idx)
                if output_item["correct_count"] <= args.threshold:
                    hard_items.append(output_item)
                    hard_batch_buffer.append(output_item)
                else:
                    other_items.append(output_item)
                    other_batch_buffer.append(output_item)
                
                processed_count += 1
                
                # 批量保存
                if processed_count % batch_size == 0:
                    if hard_batch_buffer:
                        _save_results_batch(hard_batch_buffer, args.hard_output, is_final=False)
                        hard_batch_buffer.clear()
                    if other_batch_buffer:
                        _save_results_batch(other_batch_buffer, args.other_output, is_final=False)
                        other_batch_buffer.clear()
                    logging.info(f"已处理 {processed_count}/{len(indexed_items)} 条题目，已批量保存")
            except Exception as e:
                item_id = item.get("question_id") or item.get("id") or f"idx_{idx}"
                logging.error(f"处理题目 {item_id} 时出错: {e}", exc_info=True)
                error_item = build_output_item(
                    base_item=item,
                    profile=args.profile,
                    model_name=args.model,
                    n_runs=args.n_runs,
                    correct_count=0,
                    run_details=[{"run_index": 0, "error": str(e)}],
                )
                hard_items.append(error_item)
                hard_batch_buffer.append(error_item)
                processed_count += 1
                
                # 批量保存错误条目
                if processed_count % batch_size == 0:
                    if hard_batch_buffer:
                        _save_results_batch(hard_batch_buffer, args.hard_output, is_final=False)
                        hard_batch_buffer.clear()
    
    # 保存剩余的数据
    if hard_batch_buffer:
        _save_results_batch(hard_batch_buffer, args.hard_output, is_final=False)
    if other_batch_buffer:
        _save_results_batch(other_batch_buffer, args.other_output, is_final=False)

    # 最终保存所有结果
    # 注意：在续跑模式下，hard_items 和 other_items 包含从文件加载的数据和新处理的数据
    # _save_results_batch 会读取文件并合并，确保不会重复保存
    _safe_mkdir(args.hard_output)
    _safe_mkdir(args.other_output)

    _save_results_batch(hard_items, args.hard_output, is_final=True)
    _save_results_batch(other_items, args.other_output, is_final=True)

    # 读取最终的数据量（从文件读取，确保准确）
    def _count_items_in_file(path: str) -> int:
        if not os.path.exists(path):
            return 0
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return len(data) if isinstance(data, list) else 0
        except Exception:
            return 0
    
    hard_count = _count_items_in_file(args.hard_output)
    other_count = _count_items_in_file(args.other_output)

    # 记录统计信息（仅在 detailed 模式下记录到详细日志）
    if args.log_mode == "detailed":
        stats_text = f"""处理完成！
正确次数 <= {args.threshold} 的题目（hard）: {hard_count} 条
正确次数 > {args.threshold} 的题目（other）: {other_count} 条
总计: {hard_count + other_count} 条
hard_output: {os.path.abspath(args.hard_output)}
other_output: {os.path.abspath(args.other_output)}
"""
        log_stats(stats_text)
    
    # 输出最终统计信息（使用从文件读取的数据，确保包含续跑模式下的历史数据）
    logging.info(
        f"完成！正确次数 <= {args.threshold} 的题目 {hard_count} 条，其他题目 {other_count} 条。"
    )
    logging.info(f"hard_output:  {os.path.abspath(args.hard_output)}")
    logging.info(f"other_output: {os.path.abspath(args.other_output)}")
    
    # 如果是 detailed 模式，关闭详细日志文件
    if args.log_mode == "detailed":
        close_log_file()


if __name__ == "__main__":
    main()
