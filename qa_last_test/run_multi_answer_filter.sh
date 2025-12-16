#!/bin/bash

# ==============================================================================
# 多次回答筛题脚本封装
# 使用 multi_answer_filter.py 对评测集每道题用同一模型回答 N 次，
# 按「正确次数 <= 阈值」和「> 阈值」分别输出到两个文件。
# ==============================================================================

set -eu

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ======================== 可配置区域 ========================

# 输入评测集（支持 .json/.jsonl/.csv），建议用 evaluate 里已经转换好的标准格式
INPUT_FILE="/nfsdata-117/Project/DeepEyes_Benchmark/QA-Check/qiqi/pure_image_L4.jsonl"

# 使用的模型（必须在 evaluate/config.py 的 API_CONFIG 中配置）
MODEL_NAME="qwen3-vl-plus"

# 用户画像（beginner / retail / expert / expert_cot）
PROFILE="expert"

# 每道题重复回答次数 N
N_RUNS=2

# 阈值 a：正确次数 <= a 的题目归为「hard」，其余归为「other」
THRESHOLD=1

# 并行处理的题目数量（默认1为串行，建议根据API限流和机器性能设置，如4、8等）
WORKERS=4

# 限制处理的题目数量：
# - 设为数字（如 "10"）表示只处理前 N 条（或随机抽样 N 条）
# - 设为空字符串 "" 表示处理全部
LIMIT="2"

# 是否在抽样前随机打乱题目顺序，仅当 LIMIT 有效时才有意义
USE_RANDOM=true

# 随机种子（仅当 USE_RANDOM=true 且 LIMIT 非空时有效）
SEED="42"

# 断点续跑：true=如果输出文件已存在，则加载已完成题目并跳过，只补充未完成部分；false=每次全新跑
RESUME=false

# 输出目录（可以自己设置为任意文件夹，支持绝对/相对路径）
# - 例如：OUTPUT_DIR="$SCRIPT_DIR/outputs_multi_runs"
# - 不同任务建议改个子目录名，避免混在一起
OUTPUT_DIR="$SCRIPT_DIR/outputs/测试"

# 日志目录（会传给 Python，默认为脚本目录下 logs，如果这里留空） 
LOG_DIR="$SCRIPT_DIR/logs"

# ======================== 运行检查 =========================

if [ ! -f "$INPUT_FILE" ]; then
  echo "❌ 找不到输入文件: $INPUT_FILE"
  exit 1
fi

echo "=============================================================================="
echo "多次回答筛题配置"
echo "=============================================================================="
echo "项目根目录 : $PROJECT_ROOT"
echo "输入文件   : $INPUT_FILE"
echo "模型       : $MODEL_NAME"
echo "画像       : $PROFILE"
echo "重复次数 N : $N_RUNS"
echo "阈值 a     : $THRESHOLD"
echo "并行workers: $WORKERS"
echo "LIMIT      : ${LIMIT:-<全部>}"
echo "USE_RANDOM : $USE_RANDOM"
echo "SEED       : $SEED"
echo "RESUME     : $RESUME"
echo "输出目录   : $OUTPUT_DIR"
echo "日志目录   : ${LOG_DIR:-$SCRIPT_DIR/logs}"
echo "hard输出   : (稍后根据是否续跑/版本号确定)"
echo "other输出  : (稍后根据是否续跑/版本号确定)"
echo "=============================================================================="
echo

cd "$PROJECT_ROOT"

# 确保输出目录存在
mkdir -p "$OUTPUT_DIR"

# 辅助函数：如果文件已存在，则自动生成 _v2、_v3 等新版本路径
get_next_version_path() {
  local original="$1"
  if [ ! -e "$original" ]; then
    echo "$original"
    return
  fi

  local dir name ext counter candidate
  dir="$(dirname "$original")"
  name="$(basename "$original")"
  ext=""
  if [[ "$name" == *.* ]]; then
    ext=".${name##*.}"
    name="${name%.*}"
  fi

  counter=2
  while true; do
    candidate="$dir/${name}_v${counter}${ext}"
    if [ ! -e "$candidate" ]; then
      echo "$candidate"
      return
    fi
    counter=$((counter + 1))
  done
}

# 基础文件名（不带版本号）
BASE_HARD_OUTPUT="$OUTPUT_DIR/hard_questions.json"
BASE_OTHER_OUTPUT="$OUTPUT_DIR/other_questions.json"

if [ "$RESUME" = true ]; then
  # 续跑模式：始终在同一个文件上续写，由 Python 负责读取已完成记录
  HARD_OUTPUT="$BASE_HARD_OUTPUT"
  OTHER_OUTPUT="$BASE_OTHER_OUTPUT"
else
  # 非续跑模式：如果文件已存在，则自动生成 _v2、_v3 等新文件，避免覆盖
  HARD_OUTPUT="$(get_next_version_path "$BASE_HARD_OUTPUT")"
  OTHER_OUTPUT="$(get_next_version_path "$BASE_OTHER_OUTPUT")"
fi

echo "实际 hard 输出文件 : $HARD_OUTPUT"
echo "实际 other 输出文件: $OTHER_OUTPUT"
echo

# 构建 Python 参数，方便按条件追加
PY_ARGS=(
  --input_file "$INPUT_FILE"
  --model "$MODEL_NAME"
  --profile "$PROFILE"
  --n_runs "$N_RUNS"
  --threshold "$THRESHOLD"
  --workers "$WORKERS"
  --hard_output "$HARD_OUTPUT"
  --other_output "$OTHER_OUTPUT"
)

if [ -n "$LOG_DIR" ]; then
  mkdir -p "$LOG_DIR"
  PY_ARGS+=(--log_dir "$LOG_DIR")
fi

if [ -n "${LIMIT}" ]; then
  PY_ARGS+=(--limit "$LIMIT")
  if [ "$USE_RANDOM" = true ]; then
    PY_ARGS+=(--use_random --seed "$SEED")
  fi
fi

if [ "$RESUME" = true ]; then
  PY_ARGS+=(--resume)
fi

python "$SCRIPT_DIR/multi_answer_filter.py" "${PY_ARGS[@]}"

echo
echo "✅ 运行完成。结果已写入："
echo "  - hard : $HARD_OUTPUT"
echo "  - other: $OTHER_OUTPUT"

