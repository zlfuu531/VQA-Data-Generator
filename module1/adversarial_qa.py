import argparse
import json
import os
import random
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

from qa_make import GLOBAL_CONFIG, QUESTION_TYPES, encode_image, get_prompt_template


def _extract_json_block(text: str) -> Optional[Dict[str, Any]]:
    """从模型返回的文本中提取首个 JSON 对象，容错处理引号与空白。"""
    if not text:
        return None
    start = text.find("{")
    if start == -1:
        return None

    stack = []
    in_string = False
    escape = False
    for idx, ch in enumerate(text[start:], start=start):
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
        if in_string:
            continue
        if ch == "{":
            stack.append(ch)
        elif ch == "}":
            if not stack:
                return None
            stack.pop()
            if not stack:
                try:
                    return json.loads(text[start : idx + 1])
                except Exception:
                    return None
    return None


def _ensure_client(client: Optional[OpenAI] = None) -> OpenAI:
    """优先使用传入 client，否则根据 GLOBAL_CONFIG 构建。"""
    if client:
        return client
    return OpenAI(
        api_key=GLOBAL_CONFIG.get("api_key") or os.environ.get("API_KEY", ""),
        base_url=GLOBAL_CONFIG.get("api_base", ""),
    )


def _call_model_with_image(
    client: OpenAI, prompt: str, base64_image: str, mime_type: str
) -> Dict[str, Any]:
    resp = client.chat.completions.create(
        model=GLOBAL_CONFIG.get("model_name"),
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{base64_image}"}},
                ],
            }
        ],
        max_tokens=GLOBAL_CONFIG.get("max_tokens", 8192),
        temperature=GLOBAL_CONFIG.get("temperature", 0.7),
        timeout=GLOBAL_CONFIG.get("request_timeout", 1000.0),
    )
    message = resp.choices[0].message
    return {
        "raw": message.content or "",
        "json": _extract_json_block(message.content or ""),
        "usage": getattr(resp, "usage", None),
    }


def generate_adversarial_qa(
    item: Dict[str, Any],
    image_type: str,
    question_type: str,
    max_rounds: int = 3,
    client: Optional[OpenAI] = None,
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    使用“出题者A vs 答题者B”对抗式迭代，自动找到“最难但可答”的题目。
    输入/输出字段完全复用 qa_make.py 的格式；返回 (最终问答字典, 迭代轨迹)。
    """
    qa_client = _ensure_client(client)

    base64_image, mime_type = encode_image(item.get("image_path", ""))
    if not base64_image:
        return None, []
    mime_type = mime_type or "image/jpeg"

    rounds = GLOBAL_CONFIG.get("rounds", 3)
    include_process = GLOBAL_CONFIG.get("include_process", True)
    template = get_prompt_template(image_type, question_type, rounds=rounds, include_process=include_process)

    hardening_note = "初始要求：难度需明显高于研究员，必须多信息源+多步计算。"
    trace: List[Dict[str, Any]] = []
    final_payload: Optional[Dict[str, Any]] = None

    for r in range(1, max_rounds + 1):
        a_prompt = (
            "角色A（出题者）：请基于下述出题规范与图片，生成一道极难但可答的题目，"
            "并给出标准答案和推理过程。若非选择题，可省略 options。务必输出 JSON，对象包含："
            '{"question_payload":{完整题目对象},'
            '"why_hard":"简述难点",'
            '"quality_risk":"潜在歧义或数据缺口"}。\n\n'
            f"【出题规范】\n{template}\n\n【加难指令】{hardening_note}"
        )
        a_resp = _call_model_with_image(qa_client, a_prompt, base64_image, mime_type)
        payload = (a_resp.get("json") or {}).get("question_payload")
        if not isinstance(payload, dict):
            trace.append(
                {"round": r, "status": "generate_failed", "detail": a_resp.get("raw", "")}
            )
            break

        b_prompt = (
            "角色B（答题者）：仅依据题目与图片作答，输出 JSON："
            '{"b_answer":"答案字符串或轮次字典","b_process":"简要推理链","confidence":0-1}。'
            "保持与题目相同的题型格式，不要生成新问题。"
        )
        b_resp = _call_model_with_image(qa_client, json.dumps(payload, ensure_ascii=False) + "\n\n" + b_prompt, base64_image, mime_type)
        b_json = b_resp.get("json") or {}

        judge_prompt = (
            "角色A复审：比较出题答案与B的回答，判断是否被轻松答对。"
            "请输出 JSON："
            '{"status":"too_easy|accepted|need_fix",'
            '"hardening_hint":"若too_easy，如何收紧约束/增加跨子图/多步计算",'
            '"final_payload":{经修订且合规的题目对象（修正答案/过程/选项格式）},'
            '"diagnosis":"简述B回答的优缺点"}。'
            "必须保持题型与字段格式与出题规范一致。若题目不合法，重写后放入 final_payload。"
        )
        judge_input = (
            f"【出题答案】\n{json.dumps(payload, ensure_ascii=False)}\n\n"
            f"【B的回答】\n{json.dumps(b_json, ensure_ascii=False)}\n\n"
            f"【出题规范】\n{template}"
        )
        judge_resp = _call_model_with_image(qa_client, judge_input + "\n\n" + judge_prompt, base64_image, mime_type)
        judge_json = judge_resp.get("json") or {}

        status = judge_json.get("status")
        final_payload = judge_json.get("final_payload") if isinstance(judge_json.get("final_payload"), dict) else payload
        trace.append(
            {
                "round": r,
                "status": status or "unknown",
                "hardening_hint": judge_json.get("hardening_hint", ""),
                "diagnosis": judge_json.get("diagnosis", ""),
                "b_answer": b_json.get("b_answer"),
                "b_confidence": b_json.get("confidence"),
            }
        )

        if status == "too_easy" and r < max_rounds:
            hardening_note = judge_json.get("hardening_hint", "增加跨子图、多指标链式推理。")
            continue
        break

    return final_payload, trace


def _normalize_payload(
    payload: Dict[str, Any],
    item: Dict[str, Any],
    question_type_key: str,
    question_index: int = 0,
) -> Dict[str, Any]:
    """对齐 qa_make 的字段与顺序，保证输出一致性。"""
    image_id = str(item.get("id", "unknown"))
    image_path = item.get("image_path")
    image_type = item.get("image_type")
    image_type = image_type if image_type not in (None, "all") else question_type_key and item.get("type") or "mixed"

    qt_cn = QUESTION_TYPES.get(question_type_key, payload.get("question_type", "问答题"))
    question_id = payload.get("question_id") or f"{image_id}_{question_type_key}_{question_index}"

    normalized = {
        "image_id": image_id,
        "image_path": image_path,
        "image_type": image_type or "mixed",
        "question_id": question_id,
        "question_type": qt_cn,
        "question": payload.get("question", ""),
        "options": payload.get("options"),
        "answer": payload.get("answer", ""),
    }

    if GLOBAL_CONFIG.get("include_process", True) and payload.get("qa_make_process"):
        normalized["qa_make_process"] = payload.get("qa_make_process")

    return normalized


def _load_input(path: str) -> List[Dict[str, Any]]:
    if path.lower().endswith(".jsonl"):
        data = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data.append(json.loads(line))
        return data
    with open(path, "r", encoding="utf-8") as f:
        obj = json.load(f)
    if isinstance(obj, dict) and "items" in obj:
        return obj["items"]
    if isinstance(obj, list):
        return obj
    raise ValueError("输入 JSON 格式不正确，需为数组或包含 items 字段的对象")


def _write_jsonl(path: str, item: Dict[str, Any]) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description="对抗式出题（A/B 找茬）")
    parser.add_argument("--input", required=True, help="输入JSON/JSONL")
    parser.add_argument("--output", required=True, help="输出JSONL")
    parser.add_argument("--image_type", default="mixed")
    parser.add_argument("--question_type", default="essay")
    parser.add_argument("--num", type=int, default=1, help="每张图生成题目数量（兼容 qa_make，仅取1）")
    parser.add_argument("--workers", type=int, default=1, help="兼容参数，占位")
    parser.add_argument("--batch", type=int, default=10, help="兼容参数，占位")
    parser.add_argument("--log_dir", type=str, default="./logs", help="兼容参数，占位")
    parser.add_argument("--log_mode", type=str, default="simple", choices=["simple", "detailed"], help="兼容参数，占位")
    parser.add_argument("--resume", action="store_true", help="断点续传：不清空已存在的输出文件")
    parser.add_argument("--max_rounds", type=int, default=3, help="A/B 找茬迭代轮数上限")
    parser.add_argument("--rounds", type=int, default=GLOBAL_CONFIG["rounds"])
    parser.add_argument("--api_base", default="https://dashscope.aliyuncs.com/compatible-mode/v1")
    parser.add_argument("--api_key", default="EMPTY")
    parser.add_argument("--model", default="qwen3-vl-plus")
    parser.add_argument("--temp", type=float, default=GLOBAL_CONFIG["temperature"])
    parser.add_argument("--tokens", type=int, default=GLOBAL_CONFIG["max_tokens"])
    parser.add_argument("--timeout", type=float, default=GLOBAL_CONFIG["request_timeout"])
    parser.add_argument("--retries", type=int, default=GLOBAL_CONFIG["max_retries"])
    parser.add_argument("--retry_sleep", type=float, default=GLOBAL_CONFIG["retry_sleep"])
    parser.add_argument("--enable_thinking", action="store_true")
    parser.add_argument("--no_process", action="store_true")
    parser.add_argument("--emit_trace", action="store_true", help="是否将trace也写入输出文件")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--random", action="store_true")
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()

    # 注入配置
    GLOBAL_CONFIG["api_base"] = args.api_base
    GLOBAL_CONFIG["api_key"] = args.api_key
    GLOBAL_CONFIG["model_name"] = args.model
    GLOBAL_CONFIG["temperature"] = args.temp
    GLOBAL_CONFIG["max_tokens"] = args.tokens
    GLOBAL_CONFIG["request_timeout"] = args.timeout
    GLOBAL_CONFIG["max_retries"] = args.retries
    GLOBAL_CONFIG["retry_sleep"] = args.retry_sleep
    GLOBAL_CONFIG["enable_thinking"] = args.enable_thinking
    GLOBAL_CONFIG["include_process"] = not args.no_process
    GLOBAL_CONFIG["rounds"] = args.rounds
    GLOBAL_CONFIG["questions_per_image"] = max(1, args.num)

    items = _load_input(args.input)

    if args.seed is not None:
        random.seed(args.seed)
    if args.random:
        random.shuffle(items)
    if args.limit is not None:
        items = items[: args.limit]

    # 保证输出目录存在
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    if os.path.exists(args.output) and not args.resume:
        open(args.output, "w", encoding="utf-8").close()

    for idx, item in enumerate(items, 1):
        final_payload, trace = generate_adversarial_qa(
            item,
            image_type=args.image_type,
            question_type=args.question_type,
            max_rounds=args.max_rounds,
        )
        if not final_payload:
            print(f"❌ image_id={item.get('id','unknown')} 生成失败")
            continue

        normalized = _normalize_payload(final_payload, item, args.question_type, question_index=0)
        _write_jsonl(args.output, normalized)
        print(f"✅ [{idx}/{len(items)}] image_id={item.get('id','unknown')} 已写入")

        if args.emit_trace:
            _write_jsonl(args.output, {"trace_image_id": item.get("id"), "trace": trace})


if __name__ == "__main__":
    main()


__all__ = ["generate_adversarial_qa"]

