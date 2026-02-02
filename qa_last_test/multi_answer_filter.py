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


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
EVAL_PKG_DIR = os.path.join(SCRIPT_DIR, "evaluate_py")

# 确保可以 import qa_last_test/evaluate_py 下的模块
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

try:
    from evaluate_py.data_loader import load_and_validate  # type: ignore
    from evaluate_py import config as eval_config  # type: ignore
    from evaluate_py.evaluator import evaluate_single_item  # type: ignore
except ImportError as e:  # pragma: no cover - 环境导入错误直接抛出
    raise ImportError(f"无法导入 qa_last_test/evaluate_py 模块，请确认目录结构。原始错误: {e}")

# 导入详细日志模块
from logger import (
    init_log_file,
    log_question_start,
    log_run_attempt,
    log_single_round_response,
    log_single_round_response_simple,
    log_question_summary,
    log_stats,
    close_log_file,
    attach_external_detailed_log
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
    full_result = evaluate_single_item(
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
        "--output_format",
        type=str,
        default="json",
        choices=["json", "jsonl"],
        help="输出格式：json（数组）或 jsonl（逐行JSON，追加写更不易丢失），默认 json",
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
        # detailed 模式：创建唯一的详细日志文件，并把 evaluate_py 的详细日志输出桥接到同一个文件
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
            log_mode=args.log_mode,
        )
        try:
            from evaluate_py import logger as eval_logger  # type: ignore

            attach_external_detailed_log(eval_logger)
            # 方案：只保留一个详细日志文件。
            # 注意：这里绝不能调用 evaluate_py.logger.close_detailed_log_file()。
            # 因为我们已经把 evaluate_py.logger.DETAILED_LOG_FILE 桥接到本脚本的 LOG_FILE，
            # 调用 close_detailed_log_file 会把同一个句柄关掉，导致多线程写日志时报 "I/O operation on closed file"。
        except Exception as e:
            logging.warning(f"无法桥接 evaluate_py 详细日志（将仅保留 multi_answer_filter 日志）: {e}")

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

    # 辅助函数定义（必须在 resume 读取之前定义）
    def _safe_mkdir(path: str) -> None:
        dir_path = os.path.dirname(os.path.abspath(path))
        if dir_path and not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)

    def _load_json_list_safely(path: str) -> List[Dict[str, Any]]:
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return [x for x in data if isinstance(x, dict)]
            logging.warning(f"输出文件内容不是 list，将忽略并当作空文件处理: {path}")
            return []
        except Exception as e:
            logging.warning(f"读取输出文件失败，将忽略并当作空文件处理: {path}，错误: {e}")
            return []

    def _atomic_write_json(path: str, data: Any) -> None:
        _safe_mkdir(path)
        tmp_path = path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)

    def _count_items_in_file(path: str) -> int:
        if not os.path.exists(path):
            return 0
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return len(data) if isinstance(data, list) else 0
        except Exception:
            return 0

    def _extract_qid(item: Dict[str, Any]) -> str:
        return (
            item.get("question_id")
            or item.get("id")
            or item.get("image_id")
            or ""
        )

    def _append_jsonl(output_path: str, rows: List[Dict[str, Any]]) -> None:
        _safe_mkdir(output_path)
        with open(output_path, "a", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _load_jsonl_seen_ids(path: str) -> set[str]:
        seen: set[str] = set()
        if not os.path.exists(path):
            return seen
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        if isinstance(obj, dict):
                            qid = _extract_qid(obj)
                            if qid:
                                seen.add(qid)
                    except Exception:
                        continue
        except Exception as e:
            logging.warning(f"读取输出JSONL失败，将忽略并当作空文件处理: {path}，错误: {e}")
        return seen

    # 断点续跑：如果开启，则从已有输出文件中恢复已完成题目
    processed_ids: set[str] = set()

    hard_items: List[Dict[str, Any]] = []
    other_items: List[Dict[str, Any]] = []

    if args.resume:
        # 续跑模式：从 hard_output 和 other_output 两个文件中读取已完成的 question_id
        # json：读取整个数组
        # jsonl：逐行解析，遇到损坏行会跳过
        hard_items = []
        other_items = []

        if (args.output_format or "json").lower() == "jsonl" or args.hard_output.endswith(".jsonl"):
            processed_ids |= _load_jsonl_seen_ids(args.hard_output)
            processed_ids |= _load_jsonl_seen_ids(args.other_output)
            logging.info(
                f"断点续跑开启(JSONL)：已从历史结果中扫描已完成题目数（去重）={len(processed_ids)}"
            )
        else:
            hard_items = _load_json_list_safely(args.hard_output)
            other_items = _load_json_list_safely(args.other_output)

            for it in hard_items:
                qid = _extract_qid(it)
                if qid:
                    processed_ids.add(qid)
            for it in other_items:
                qid = _extract_qid(it)
                if qid:
                    processed_ids.add(qid)

            logging.info(
                f"断点续跑开启(JSON)：已从历史结果中加载 "
                f"hard_items={len(hard_items)}, other_items={len(other_items)}, "
                f"已完成题目数（去重）={len(processed_ids)}"
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

    # 辅助函数定义（续跑/写入逻辑使用上方同名函数，避免重复定义导致维护混乱）

    def _save_results_batch(items: List[Dict[str, Any]], output_path: str, is_final: bool = False):
        """保存结果：支持 json（数组）/ jsonl（逐行追加）。

        - json：读全量 -> qid去重合并 -> 原子替换
        - jsonl：逐条追加写入（更抗中断）；续跑依赖从文件扫描已完成 qid
        """
        try:
            fmt = (args.output_format or "json").lower()
            if fmt == "jsonl" or output_path.endswith(".jsonl"):
                # jsonl 采用追加写；调用方应确保 items 内不重复（我们也做一次本批去重）
                batch_dict: Dict[str, Dict[str, Any]] = {}
                for it in items:
                    if not isinstance(it, dict):
                        continue
                    qid = _extract_qid(it)
                    if not qid:
                        logging.warning(f"发现缺少有效ID的输出项，已跳过保存: {it}")
                        continue
                    batch_dict[qid] = it
                if batch_dict:
                    _append_jsonl(output_path, list(batch_dict.values()))
                    logging.info(f"追加写入 {output_path}: 本批 {len(batch_dict)} 条")
                return

            # 默认 json 数组格式
            existing_items = _load_json_list_safely(output_path)

            items_dict: Dict[str, Dict[str, Any]] = {}
            for it in existing_items:
                qid = _extract_qid(it)
                if qid:
                    items_dict[qid] = it

            new_count = 0
            for it in items:
                if not isinstance(it, dict):
                    continue
                qid = _extract_qid(it)
                if not qid:
                    logging.warning(f"发现缺少有效ID的输出项，已跳过保存: {it}")
                    continue
                if qid not in items_dict:
                    new_count += 1
                items_dict[qid] = it

            all_items = list(items_dict.values())
            _atomic_write_json(output_path, all_items)

            if new_count > 0 or is_final:
                logging.info(f"保存到 {output_path}: 新增 {new_count} 条，总计 {len(all_items)} 条")
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
        """处理单个题目：每题 n_runs 并行执行，聚合结果后输出。"""
        item_id = (
            item.get("question_id")
            or item.get("id")
            or item.get("image_id")
            or f"idx_{idx}"
        )
        logging.info(f"=== 处理题目 {idx}/{len(items)}: question_id={item_id} ===")

        question = item.get("question", "")
        answer = item.get("answer", "")
        is_multi_round = isinstance(question, dict) or isinstance(answer, dict)

        question_preview = str(question)[:200] if question else ""
        log_question_start(
            question_id=item_id,
            question_num=idx,
            total_questions=len(items),
            is_multi_round=is_multi_round,
            question_preview=question_preview,
        )

        def _run_one(run_idx: int):
            try:
                full_result, model_data, is_correct = run_single_attempt(item, args.model, args.profile)
            except Exception as e:
                full_result, model_data, is_correct = {"error": str(e)}, {"error": str(e)}, False

            # 记录本次回答尝试
            log_run_attempt(
                question_id=item_id,
                question_num=idx,
                run_index=run_idx,
                n_runs=args.n_runs,
                is_correct=is_correct,
            )

            run_entry: Dict[str, Any] = {"run_index": run_idx}

            if isinstance(model_data, dict):
                is_mr = model_data.get("is_multi_round", False)
                rounds = model_data.get("rounds", [])

                if is_mr and isinstance(rounds, list) and len(rounds) > 0:
                    processed_rounds_dict: Dict[str, Dict[str, Any]] = {}
                    for r_i, round_item in enumerate(rounds, 1):
                        processed_round = round_item.copy()

                        raw_response = processed_round.get("raw_response")
                        judge_response = processed_round.get("judge_response")
                        round_key = processed_round.get("round", f"round{r_i}")
                        round_prompt = processed_round.get("prompt", "")
                        round_model_answer = processed_round.get("model_answer", "")
                        round_extracted_answer = processed_round.get("extracted_answer", "")
                        round_is_correct = processed_round.get("is_correct", False)
                        round_judge_reasoning = processed_round.get("judge_reasoning", "")

                        log_single_round_response(
                            question_id=item_id,
                            question_num=idx,
                            run_index=run_idx,
                            round_key=round_key,
                            round_num=r_i,
                            prompt=round_prompt,
                            raw_response=raw_response,
                            judge_response=judge_response,
                            model_answer=round_model_answer,
                            extracted_answer=round_extracted_answer,
                            is_correct=round_is_correct,
                            judge_reasoning=round_judge_reasoning,
                        )

                        round_process = _build_process_from_round_data(round_item)
                        if round_process:
                            processed_round["process"] = round_process

                        processed_round.pop("raw_response", None)
                        processed_round.pop("judge_response", None)
                        processed_round.pop("conversation_history", None)
                        processed_round.pop("round", None)

                        processed_rounds_dict[round_key] = processed_round

                    run_entry["rounds"] = processed_rounds_dict
                    for key in ["is_multi_round", "all_rounds_correct", "total_response_time", "total_judge_time"]:
                        if key in model_data:
                            run_entry[key] = model_data[key]
                else:
                    raw_response = model_data.get("raw_response")
                    judge_response = model_data.get("judge_response")
                    prompt = model_data.get("prompt", "")
                    model_answer = model_data.get("model_answer", "")
                    extracted_answer = model_data.get("extracted_answer", "")
                    judge_reasoning = model_data.get("judge_reasoning", "")

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
                        judge_reasoning=judge_reasoning,
                    )

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

                    process_text = _build_process_from_model_data(model_data)
                    if process_text:
                        run_entry["process"] = process_text

            run_entry["is_correct"] = bool(is_correct)
            return run_idx, run_entry, bool(is_correct)

        # 题内并行执行 n_runs
        run_results: List[Tuple[int, Dict[str, Any], bool]] = []
        with ThreadPoolExecutor(max_workers=args.n_runs) as run_executor:
            futures = [run_executor.submit(_run_one, r) for r in range(1, args.n_runs + 1)]
            for f in as_completed(futures):
                run_results.append(f.result())

        run_results.sort(key=lambda x: x[0])
        run_details = [x[1] for x in run_results]
        correct_count = sum(1 for x in run_results if x[2])

        log_question_summary(
            question_id=item_id,
            question_num=idx,
            correct_count=correct_count,
            n_runs=args.n_runs,
            threshold=args.threshold,
        )

        output_item = build_output_item(
            base_item=item,
            profile=args.profile,
            model_name=args.model,
            n_runs=args.n_runs,
            correct_count=correct_count,
            run_details=run_details,
        )

        return output_item

    # 注意：hard_items / other_items 可能已在断点续跑时加载了历史数据，这里不要重新置空。

    # 写入策略：
    # - json  : 走 batch 合并写（避免每条都重写全量文件）
    # - jsonl : 每道题完成后立即追加写入（抗中断），并发时通过锁保证写入原子性
    batch_size = args.batch_size
    hard_batch_buffer = []
    other_batch_buffer = []
    processed_count = 0

    jsonl_write_lock = None
    is_jsonl_mode = (args.output_format or "json").lower() == "jsonl" or args.hard_output.endswith(".jsonl")
    if is_jsonl_mode:
        import threading

        jsonl_write_lock = threading.Lock()

    # 并行处理题目（两层并行：题目并行 * 题内 n_runs 并行）
    if args.workers < args.n_runs:
        raise ValueError(
            f"workers({args.workers}) 必须 >= n_runs({args.n_runs})，否则无法保证每题 n_runs 并行且总并发不超过 workers。"
        )

    question_workers = max(1, args.workers // args.n_runs)
    logging.info(
        f"并行策略: total_workers={args.workers}, n_runs={args.n_runs}, question_workers={question_workers} "
        f"(≈ floor(workers/n_runs))"
    )

    if question_workers > 1:
        logging.info(f"使用并行处理（题目并行），question_workers={question_workers}")
        with ThreadPoolExecutor(max_workers=question_workers) as executor:
            futures = {
                executor.submit(process_single_item, item, idx): (idx, item)
                for idx, item in indexed_items
            }

            for future in tqdm(as_completed(futures), total=len(indexed_items), desc="处理题目"):
                idx, item = futures[future]
                try:
                    output_item = future.result()
                    qid = _extract_qid(output_item)

                    if output_item["correct_count"] <= args.threshold:
                        hard_items.append(output_item)
                        if is_jsonl_mode:
                            assert jsonl_write_lock is not None
                            with jsonl_write_lock:
                                _append_jsonl(args.hard_output, [output_item])
                            logging.info(f"已写入(JSONL) hard: question_id={qid}, correct_count={output_item['correct_count']}")
                        else:
                            hard_batch_buffer.append(output_item)
                    else:
                        other_items.append(output_item)
                        if is_jsonl_mode:
                            assert jsonl_write_lock is not None
                            with jsonl_write_lock:
                                _append_jsonl(args.other_output, [output_item])
                            logging.info(f"已写入(JSONL) other: question_id={qid}, correct_count={output_item['correct_count']}")
                        else:
                            other_batch_buffer.append(output_item)

                    processed_count += 1

                    # json 模式：批量保存
                    if (not is_jsonl_mode) and processed_count % batch_size == 0:
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
                    processed_count += 1

                    if is_jsonl_mode:
                        assert jsonl_write_lock is not None
                        with jsonl_write_lock:
                            _append_jsonl(args.hard_output, [error_item])
                        logging.info(f"已写入(JSONL) hard(error): question_id={_extract_qid(error_item)}, correct_count=0")
                    else:
                        hard_batch_buffer.append(error_item)
                        # 批量保存错误条目
                        if processed_count % batch_size == 0:
                            if hard_batch_buffer:
                                _save_results_batch(hard_batch_buffer, args.hard_output, is_final=False)
                                hard_batch_buffer.clear()
    else:
        # 串行处理（题目串行，但题内仍是 n_runs 并行）
        logging.info("使用串行处理（题目串行，题内并行）")
        for idx, item in indexed_items:
            try:
                output_item = process_single_item(item, idx)
                qid = _extract_qid(output_item)

                if output_item["correct_count"] <= args.threshold:
                    hard_items.append(output_item)
                    if is_jsonl_mode:
                        assert jsonl_write_lock is not None
                        with jsonl_write_lock:
                            _append_jsonl(args.hard_output, [output_item])
                        logging.info(f"已写入(JSONL) hard: question_id={qid}, correct_count={output_item['correct_count']}")
                    else:
                        hard_batch_buffer.append(output_item)
                else:
                    other_items.append(output_item)
                    if is_jsonl_mode:
                        assert jsonl_write_lock is not None
                        with jsonl_write_lock:
                            _append_jsonl(args.other_output, [output_item])
                        logging.info(f"已写入(JSONL) other: question_id={qid}, correct_count={output_item['correct_count']}")
                    else:
                        other_batch_buffer.append(output_item)

                processed_count += 1

                # json 模式：批量保存
                if (not is_jsonl_mode) and processed_count % batch_size == 0:
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
                processed_count += 1

                if is_jsonl_mode:
                    assert jsonl_write_lock is not None
                    with jsonl_write_lock:
                        _append_jsonl(args.hard_output, [error_item])
                    logging.info(f"已写入(JSONL) hard(error): question_id={_extract_qid(error_item)}, correct_count=0")
                else:
                    hard_batch_buffer.append(error_item)
                    if processed_count % batch_size == 0:
                        if hard_batch_buffer:
                            _save_results_batch(hard_batch_buffer, args.hard_output, is_final=False)
                            hard_batch_buffer.clear()
    
    # 保存剩余的数据
    if not is_jsonl_mode:
        if hard_batch_buffer:
            _save_results_batch(hard_batch_buffer, args.hard_output, is_final=False)
        if other_batch_buffer:
            _save_results_batch(other_batch_buffer, args.other_output, is_final=False)

    # 最终保存与统计
    _safe_mkdir(args.hard_output)
    _safe_mkdir(args.other_output)

    if not is_jsonl_mode:
        # json 模式：最终合并写入（避免重复/遗漏）
        _save_results_batch(hard_items, args.hard_output, is_final=True)
        _save_results_batch(other_items, args.other_output, is_final=True)

        def _count_json_items(path: str) -> int:
            if not os.path.exists(path):
                return 0
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return len(data) if isinstance(data, list) else 0
            except Exception:
                return 0

        hard_count = _count_json_items(args.hard_output)
        other_count = _count_json_items(args.other_output)
    else:
        # jsonl 模式：按题目即时追加写入，因此不再进行 final 追加（否则会重复写入）
        def _count_jsonl_lines(path: str) -> int:
            if not os.path.exists(path):
                return 0
            try:
                cnt = 0
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            cnt += 1
                return cnt
            except Exception:
                return 0

        hard_count = _count_jsonl_lines(args.hard_output)
        other_count = _count_jsonl_lines(args.other_output)

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
