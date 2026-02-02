import csv
import json
from pathlib import Path
from typing import Set, List


BASE_COLUMNS: List[str] = [
    "question_id", "round", "question", "answer", "question_type",
    "image_type", "image_path", "original_image_path",
    "profile", "scenario", "capability", "difficulty", "source", "language",
]


def load_incomplete_question_keys(csv_path: Path) -> Set[str]:
    """
    从汇总后的 CSV 中找出“至少有一个模型为空”的题目（按 question_id 作为键）。

    说明：
        - 任何一个模型列为空字符串或仅空白，即认为该题某模型没答；
        - 不再区分 round，只要同一 question_id 的任意一行有模型为空，
          则该 question_id 下的所有记录都视为 A 类题目。
    """
    keys: Set[str] = set()

    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []

        # 识别模型列：CSV 中除基础列外的其它列都视为模型名称
        model_columns = [c for c in fieldnames if c not in BASE_COLUMNS]

        for row in reader:
            qid = row.get("question_id", "")

            # 只要有一个模型值为空，就认为该 (qid, round) 是不完整题目
            has_empty_model = False
            for mc in model_columns:
                if mc not in row:
                    continue
                v = row[mc]
                if v is None or str(v).strip() == "":
                    has_empty_model = True
                    break

            if has_empty_model:
                keys.add(str(qid))

    return keys


def make_key_from_item(item: dict) -> str:
    """
    将 json/jsonl 里的一条题目记录转换为与 CSV 对应的键。

    这里仅按 question_id：
        - 不再区分 round，多轮题每一轮的记录都会因为同一 question_id
          被统一地保留或删除。
    """
    qid = item.get("question_id", "")
    return str(qid)


def filter_jsonl_file(jsonl_path: Path, bad_keys: Set[str]) -> None:
    """
    删除 jsonl 文件中属于 bad_keys（A 类题目）的所有记录。

    保留：
        - 第一行 statistics（原样保留，不重新计算）；
        - 其余行中，只有键不在 bad_keys 里的题目会被保留。
    """
    if not jsonl_path.exists():
        return

    with jsonl_path.open("r", encoding="utf-8") as f:
        lines = f.readlines()

    if not lines:
        return

    # 第一行统计信息原样保留
    header = lines[0]
    new_lines: List[str] = [header.rstrip("\n") + "\n"]

    removed_count = 0

    for line in lines[1:]:
        txt = line.strip()
        if not txt:
            continue
        try:
            item = json.loads(txt)
        except json.JSONDecodeError:
            # 异常行直接丢弃，避免污染
            continue

        key = make_key_from_item(item)
        if key in bad_keys:
            removed_count += 1
            continue

        new_lines.append(json.dumps(item, ensure_ascii=False) + "\n")

    # 覆盖写回
    with jsonl_path.open("w", encoding="utf-8") as f:
        f.writelines(new_lines)

    print(f"[clean] {jsonl_path} 删除 {removed_count} 条记录，保留 {len(new_lines) - 1} 条。")


def main():
    base_dir = Path("/home/zenglingfeng/qa_pipline12-7/evaluate")

    csv_path = base_dir / "outputs" / "last_evaluate12-23.csv"
    expert_dir = base_dir / "outputs" / "expert"
    pattern_name = "last_evaluate.jsonl"

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV 文件不存在: {csv_path}")
    if not expert_dir.exists():
        raise FileNotFoundError(f"expert 目录不存在: {expert_dir}")

    print(f"读取不完整题目 (A 类) 来自: {csv_path}")
    bad_keys = load_incomplete_question_keys(csv_path)
    print(f"A 类题目数量: {len(bad_keys)}")

    # 遍历所有模型子目录
    for model_dir in expert_dir.iterdir():
        if not model_dir.is_dir():
            continue
        jsonl_path = model_dir / pattern_name
        if not jsonl_path.exists():
            continue

        print(f"处理模型 {model_dir.name} 的文件: {jsonl_path}")
        filter_jsonl_file(jsonl_path, bad_keys)

    print("清理完成。")


if __name__ == "__main__":
    main()


