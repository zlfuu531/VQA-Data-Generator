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


def _strip_boxed_content(text: str) -> str:
    """移除文本中的 \\boxed{...} 片段，只保留思考/分析部分。"""
    if not text:
        return ""
    # 粗略移除所有 \\boxed{...}，只用于过程展示
    cleaned = re.sub(r"\\\\boxed\{.*?\}", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"\\boxed\{.*?\}", "", cleaned, flags=re.DOTALL)
    return cleaned.strip()


def _build_process_from_model_data(model_data: Dict[str, Any]) -> str:
    """
    从 evaluate.single_item 的 model_data 中构造本次 run 的 process：
    - 优先使用模型思考内容（reasoning_content / reasoning / reasoning_details）
    - 再拼接去掉 \\boxed{} 的正文 model_answer
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
                # 依次兼容不同字段名
                rc = msg.get("reasoning_content")
                if isinstance(rc, str) and rc.strip():
                    reasoning_text = rc.strip()
                else:
                    rc2 = msg.get("reasoning")
                    if isinstance(rc2, str) and rc2.strip():
                        reasoning_text = rc2.strip()
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

    # 单轮题：直接用 is_correct
    # 多轮题：优先用 is_correct，其次 all_rounds_correct
    is_correct = False
    if is_multi_round:
        if "is_correct" in model_data:
            is_correct = bool(model_data["is_correct"])
        elif "all_rounds_correct" in model_data:
            is_correct = bool(model_data["all_rounds_correct"])
    else:
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

    args = parser.parse_args()

    # 日志配置：既打到控制台，也写到本文件夹下的 logs 目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    log_dir = args.log_dir or os.path.join(script_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"multi_answer_filter_{timestamp}.log")

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    logging.info(f"日志写入文件: {log_file}")

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

    if not indexed_items:
        logging.info("没有需要新增处理的题目（可能全部已在历史结果中完成）。")
        # 仍然写回一次文件，保证输出存在
        def _safe_mkdir(path: str) -> None:
            dir_path = os.path.dirname(os.path.abspath(path))
            if dir_path and not os.path.exists(dir_path):
                os.makedirs(dir_path, exist_ok=True)

        _safe_mkdir(args.hard_output)
        _safe_mkdir(args.other_output)

        with open(args.hard_output, "w", encoding="utf-8") as f:
            json.dump(hard_items, f, ensure_ascii=False, indent=2)

        with open(args.other_output, "w", encoding="utf-8") as f:
            json.dump(other_items, f, ensure_ascii=False, indent=2)

        logging.info(
            f"完成！正确次数 <= {args.threshold} 的题目 {len(hard_items)} 条，其他题目 {len(other_items)} 条。"
        )
        logging.info(f"hard_output:  {os.path.abspath(args.hard_output)}")
        logging.info(f"other_output: {os.path.abspath(args.other_output)}")
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

            # 记录本次结果
            run_entry: Dict[str, Any] = {
                "run_index": run_idx,
            }
            if isinstance(model_data, dict):
                # 尽量保留关键信息，而不是所有字段（避免文件太大）
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
                    else:
                        other_items.append(output_item)
                except Exception as e:
                    item_id = item.get("question_id") or item.get("id") or f"idx_{idx}"
                    logging.error(f"处理题目 {item_id} 时出错: {e}")
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
    else:
        # 串行处理（原有逻辑）
        logging.info("使用串行处理")
        for idx, item in indexed_items:
            output_item = process_single_item(item, idx)
            if output_item["correct_count"] <= args.threshold:
                hard_items.append(output_item)
            else:
                other_items.append(output_item)

    # 写出结果
    def _safe_mkdir(path: str) -> None:
        dir_path = os.path.dirname(os.path.abspath(path))
        if dir_path and not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)

    _safe_mkdir(args.hard_output)
    _safe_mkdir(args.other_output)

    with open(args.hard_output, "w", encoding="utf-8") as f:
        json.dump(hard_items, f, ensure_ascii=False, indent=2)

    with open(args.other_output, "w", encoding="utf-8") as f:
        json.dump(other_items, f, ensure_ascii=False, indent=2)

    logging.info(
        f"完成！正确次数 <= {args.threshold} 的题目 {len(hard_items)} 条，其他题目 {len(other_items)} 条。"
    )
    logging.info(f"hard_output:  {os.path.abspath(args.hard_output)}")
    logging.info(f"other_output: {os.path.abspath(args.other_output)}")


if __name__ == "__main__":
    main()
