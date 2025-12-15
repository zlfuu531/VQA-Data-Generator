#!/usr/bin/env bash

# ==============================================================================
# 模块2：错误样本重试脚本
# ------------------------------------------------------------------------------
# 场景：
#   已经跑完一次 module2 输出目录（含 L1-L4 + summary + error.json/jsonl），
#   其中部分题目的某个模型返回了空/错误答案。此脚本只重试 error 文件里的题，
#   对已有答案的模型不会重复调用，仅为缺失/错误的模型补答，然后重新分级并写 summary。
#
# 用法：
#   1) 在项目根目录或本目录执行：bash module2/重试错误题请使用这个.sh
#   2) 修改下方用户配置 OUTPUT_DIR 指向已有输出目录（包含 error.jsonl/json）
#   3) 脚本会自动识别 jsonl/json 格式，重试完后会覆盖输出目录下的 L1-L4、error、summary
# ==============================================================================

set -euo pipefail

######################### 用户可配置区域 #########################
# 必填：已有输出目录（包含 L1-L4 与 error 文件）
OUTPUT_DIR="/home/zenglingfeng/qa_pipline12-7/output/module2/测试问题12-10_v15"

# 可选：并发与调试
WORKERS=2          # 重试并发线程数
BATCH_SIZE=4       # 虽然重试量通常不大，仍保留 batch_size 兼容
DEBUG_MODE=true    # 是否打印调试信息
OUTPUT_FORMAT=""   # 留空则自动识别（优先检测 L1.jsonl ）
######################### 用户可配置区域 #########################

######################### 内部实现（一般不改） #########################
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_ROOT}"

# 自动识别输出格式
if [ -z "${OUTPUT_FORMAT}" ]; then
  if [ -f "${OUTPUT_DIR}/L1.jsonl" ]; then
    OUTPUT_FORMAT="jsonl"
  else
    OUTPUT_FORMAT="json"
  fi
fi

echo "================================================================"
echo "🔄 开始重试 error 样本"
echo "📂 输出目录: ${OUTPUT_DIR}"
echo "📝 输出格式: ${OUTPUT_FORMAT}"
echo "⚙️  并发:     ${WORKERS}"
echo "🐞 调试:     ${DEBUG_MODE}"
echo "================================================================"

# 导出给 Python 子进程使用
export OUTPUT_DIR OUTPUT_FORMAT WORKERS BATCH_SIZE DEBUG_MODE

python - <<'PYCODE'
import os
import sys
import json

from module2.model_evaluation import Module2ModelEvaluation

output_dir = os.environ["OUTPUT_DIR"]
output_format = os.environ["OUTPUT_FORMAT"]
workers = int(os.environ.get("WORKERS", "2"))
batch_size = int(os.environ.get("BATCH_SIZE", "4"))
debug_mode = os.environ.get("DEBUG_MODE", "false").lower() == "true"

# 初始化评估器
evaluator = Module2ModelEvaluation(
    output_dir=output_dir,
    max_workers=workers,
    batch_size=batch_size,
    debug_mode=debug_mode,
)
evaluator._output_format = output_format  # 直接指定，便于复用内部加载/保存逻辑

# 读取已有结果和 error
existing_results, error_items = evaluator._load_existing_results(output_dir)
print(f"📊 现有正常样本: {len(existing_results)} | 待重试错误样本: {len(error_items)}")

if not error_items:
    print("✅ 没有需要重试的错误样本，退出")
    sys.exit(0)

# 已有结果的 ID 集合（L1-L4）
processed_ids = set()
for r in existing_results:
    rid = str(r.get("question_id") or r.get("id", ""))
    if rid:
        processed_ids.add(rid)

# 先剔除 error 文件中已在 L1-L4 出现的题（视为已处理过的残留）
pending_errors = []
skipped_already_done = 0
for item in error_items:
    rid = str(item.get("question_id") or item.get("id", ""))
    if rid and rid in processed_ids:
        skipped_already_done += 1
        continue
    pending_errors.append(item)

if skipped_already_done:
    print(f"🧹 检测到 {skipped_already_done} 条错误已在 L1-L4 中存在，先行删除不重试")

# 逐条重试待处理的错误（仅为缺失答案的模型调用，已有答案不会重复调用）
retry_results = []
for idx, item in enumerate(pending_errors, 1):
    print(f"🔁 重试 {idx}/{len(pending_errors)} | id={item.get('id') or item.get('question_id')}")
    res = evaluator.evaluate_item(item, retry_errors=True)
    retry_results.append(res)

# 合并并重新输出 L1-L4 / error / summary
all_results = existing_results + retry_results
evaluator._save_by_level_and_summary(all_results, output_dir)

# 从 error 文件中移除：
# 1) 已在 L1-L4 中存在的旧残留
# 2) 本次重试后不再有错误标记的条目
remaining_errors = []
for item in pending_errors:
    rid = str(item.get("question_id") or item.get("id", ""))
    # 找到对应的重试结果
    matched = next((r for r in retry_results if str(r.get("question_id") or r.get("id", "")) == rid), None)
    if matched:
        has_error = ("model_error" in matched) or ("error" in matched)
        if has_error:
            remaining_errors.append(matched)
    else:
        # 理论不该发生，保守保留
        remaining_errors.append(item)

# 写回或删除 error 文件
file_ext = ".jsonl" if output_format == "jsonl" else ".json"
error_path = os.path.join(output_dir, f"error{file_ext}")
if remaining_errors:
    if output_format == "jsonl":
        with open(error_path, "w", encoding="utf-8") as f:
            for item in remaining_errors:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
    else:
        with open(error_path, "w", encoding="utf-8") as f:
            json.dump(remaining_errors, f, ensure_ascii=False, indent=2)
    print(f"🧹 已更新 error 文件，剩余错误 {len(remaining_errors)} 条 -> {error_path}")
else:
    if os.path.exists(error_path):
        os.remove(error_path)
    print(f"🧹 所有错误已修复，已删除 {error_path}")

print("✅ 重试完成，已重新写入 L1-L4、error、summary")
PYCODE


