#!/bin/bash
# ==============================================================================
# 多次回答筛题脚本封装
# 使用 multi_answer_filter.py 对评测集每道题用同一模型回答 N 次，
# 按「正确次数 <= 阈值」和「> 阈值」分别输出到两个文件。
# ==============================================================================
set -eu
# 如果bash版本支持pipefail，则启用它（bash 3.0+）
if [[ "${BASH_VERSION%%.*}" -ge 3 ]] 2>/dev/null; then
    set -o pipefail
fi

# 加载通用工具函数
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
if [ -f "$SCRIPT_DIR/utils_common.sh" ]; then
    source "$SCRIPT_DIR/utils_common.sh"
elif [ -f "$PROJECT_ROOT/utils_common.sh" ]; then
    source "$PROJECT_ROOT/utils_common.sh"
else
    # 如果没有工具函数，定义基本函数
    print_error() { echo "❌ 错误：$1"; [ -n "${2:-}" ] && echo "   💡 建议：$2"; }
    print_warning() { echo "⚠️  警告：$1"; [ -n "${2:-}" ] && echo "   💡 建议：$2"; }
    print_success() { echo "✅ $1"; }
    print_info() { echo "ℹ️  $1"; }
    check_file_exists() {
        [ -f "$1" ] || { print_error "找不到文件" "路径: $1"; return 1; }
    }
    check_directory_exists() {
        [ -d "$1" ] || { print_error "目录不存在" "路径: $1"; return 1; }
    }
fi

# ======================== 可配置区域 ========================

# 输入评测集（支持 .json/.jsonl/.csv/.xlsx/.xls），建议用 evaluate 里已经转换好的标准格式
INPUT_FILE="/nfsdata-117/project/DeepEyes_Benchmark/qa_pipline12-7/qa_last_test/check_image/2-2的L3未精标.xlsx"

# 输出目录（可以自己设置为任意文件夹，支持绝对/相对路径）
# - 不同任务建议改个子目录名，避免混在一起
OUTPUT_DIR="$SCRIPT_DIR/outputs/aliyun-2-2-L3-weijingbiao"

# 输出格式：json（数组）或 jsonl（逐行JSON，追加写更不易丢失）
OUTPUT_FORMAT="jsonl"  # 可选: json / jsonl

# 使用的模型（必须在 evaluate/config.py 的 API_CONFIG 中配置）
#MODEL_NAME="qwen3-vl-235b-a22b-thinking"
MODEL_NAME="qwen3-vl-plus"

# 用户画像（beginner / retail / expert / expert_cot）
PROFILE="expert"

# 每道题重复回答次数 N
N_RUNS=5

# 阈值 a：正确次数 <= a 的题目归为「hard」，其余归为「other」
THRESHOLD=2

# 并行处理的题目数量（默认1为串行，建议根据API限流和机器性能设置，如4、8等）
WORKERS=80

# 限制处理的题目数量：
# - 设为数字（如 "10"）表示只处理前 N 条（或随机抽样 N 条）
# - 设为空字符串 "" 表示处理全部
LIMIT=""

# 是否在抽样前随机打乱题目顺序，仅当 LIMIT 有效时才有意义
USE_RANDOM=false

# 随机种子（仅当 USE_RANDOM=true 且 LIMIT 非空时有效）
SEED="42"

# 断点续跑：true=如果输出文件已存在，则加载已完成题目并跳过，只补充未完成部分；false=每次全新跑
RESUME=true

# ==============================================================================
# 日志配置
# ==============================================================================
LOG_DIR="$SCRIPT_DIR/logs"                                    # 日志目录
LOG_LEVEL="INFO"                                               # 日志级别：DEBUG/INFO/WARNING/ERROR
LOG_MODE="detailed"                                            # 日志模式：simple(简化) 或 detailed(详细)

# ==============================================================================
# 性能与批量配置
# ==============================================================================
BATCH_SIZE=10                                                  # json 模式下的批量写入大小（jsonl 模式会按题目即时写入）

# ==============================================================================
# 超时与重试配置（通过环境变量传递给 evaluate 模块）
# ==============================================================================
TIMEOUT=600                                                    # 单次API请求超时时间（秒），默认600秒
MAX_RETRIES=3                                                  # 请求失败时的最大重试次数，默认3次
RETRY_SLEEP=1.0                                                # 请求失败后的基础重试间隔（秒），后续按指数退避，默认1秒

# ==============================================================================
# 预检查
# ==============================================================================
if ! check_file_exists "$INPUT_FILE" "输入文件"; then
    exit 1
fi

# 创建必要的目录
mkdir -p "$OUTPUT_DIR"
mkdir -p "$LOG_DIR"

# ==============================================================================
# 构建环境变量（传递给 evaluate 模块）
# ==============================================================================
export EVAL_TIMEOUT="$TIMEOUT"
export EVAL_MAX_RETRIES="$MAX_RETRIES"
export EVAL_RETRY_SLEEP="$RETRY_SLEEP"
export EVAL_LOG_MODE="$LOG_MODE"
export EVAL_JUDGE_MAX_RETRIES="$MAX_RETRIES"
export EVAL_JUDGE_RETRY_DELAY="$RETRY_SLEEP"

# ==============================================================================
# 打印配置信息
# ==============================================================================
echo "=============================================================================="
echo "多次回答筛题配置"
echo "=============================================================================="
echo "项目根目录 : $PROJECT_ROOT"
echo "输入文件   : $INPUT_FILE"
echo "模型       : $MODEL_NAME"
echo "画像       : $PROFILE"
echo "重复次数 N : $N_RUNS"
echo "阈值 a     : $THRESHOLD"
echo "并行workers(总并发): $WORKERS"
echo "LIMIT      : ${LIMIT:-<全部>}"
echo "USE_RANDOM : $USE_RANDOM"
if [ "$USE_RANDOM" = "true" ]; then
    echo "SEED       : $SEED"
fi
echo "RESUME     : $RESUME"
echo "输出目录(配置)   : $OUTPUT_DIR"
echo "输出格式   : $OUTPUT_FORMAT"
echo "日志目录   : ${LOG_DIR:-$SCRIPT_DIR/logs}"
echo "日志级别   : $LOG_LEVEL"
echo "日志模式   : $LOG_MODE"
echo "批量大小   : $BATCH_SIZE"
echo ""
echo "超时与重试配置:"
echo "  超时时间: ${TIMEOUT}s"
echo "  最大重试: $MAX_RETRIES 次"
echo "  重试延迟: ${RETRY_SLEEP}s"
echo "=============================================================================="
echo

cd "$SCRIPT_DIR"

# 辅助函数：如果目录或文件已存在，则自动生成带版本号的目录路径
get_next_version_dir() {
  local base_dir="$1"
  local check_file="$2"

  if [ "$RESUME" = true ]; then
    echo "$base_dir"
    return
  fi

  if [ ! -e "$base_dir" ] && [ ! -f "$check_file" ]; then
    echo "$base_dir"
    return
  fi

  local parent_dir dir_name counter candidate
  parent_dir="$(dirname "$base_dir")"
  dir_name="$(basename "$base_dir")"

  counter=2
  while true; do
    candidate="$parent_dir/${dir_name}_v${counter}"
    candidate_file="$candidate/$(basename "$check_file")"
    if [ ! -e "$candidate" ] && [ ! -f "$candidate_file" ]; then
      echo "$candidate"
      return
    fi
    counter=$((counter + 1))
  done
}

# 根据输出格式，决定检查文件名与输出文件名
if [ "$OUTPUT_FORMAT" = "jsonl" ]; then
  CHECK_FILE="$OUTPUT_DIR/hard_questions.jsonl"
else
  CHECK_FILE="$OUTPUT_DIR/hard_questions.json"
fi

ACTUAL_OUTPUT_DIR="$(get_next_version_dir "$OUTPUT_DIR" "$CHECK_FILE")"
mkdir -p "$ACTUAL_OUTPUT_DIR"

if [ "$OUTPUT_FORMAT" = "jsonl" ]; then
  HARD_OUTPUT="$ACTUAL_OUTPUT_DIR/hard_questions.jsonl"
  OTHER_OUTPUT="$ACTUAL_OUTPUT_DIR/other_questions.jsonl"
else
  HARD_OUTPUT="$ACTUAL_OUTPUT_DIR/hard_questions.json"
  OTHER_OUTPUT="$ACTUAL_OUTPUT_DIR/other_questions.json"
fi

echo "实际输出目录 : $ACTUAL_OUTPUT_DIR"
echo "实际 hard 输出文件 : $HARD_OUTPUT"
echo "实际 other 输出文件: $OTHER_OUTPUT"

echo

# 构建 Python 参数
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
  PY_ARGS+=(--log_dir "$LOG_DIR")
fi

PY_ARGS+=(--log_level "$LOG_LEVEL")
PY_ARGS+=(--log_mode "$LOG_MODE")
PY_ARGS+=(--batch_size "$BATCH_SIZE")
PY_ARGS+=(--output_format "$OUTPUT_FORMAT")

if [ -n "${LIMIT}" ]; then
  PY_ARGS+=(--limit "$LIMIT")
  if [ "$USE_RANDOM" = true ]; then
    PY_ARGS+=(--use_random --seed "$SEED")
  fi
fi

if [ "$RESUME" = true ]; then
  PY_ARGS+=(--resume)
fi

# ==============================================================================
# 运行脚本
# ==============================================================================
echo "开始处理..."
python "$SCRIPT_DIR/multi_answer_filter.py" "${PY_ARGS[@]}"

echo
echo "=============================================================================="
echo "处理完成！"
echo "=============================================================================="
print_success "结果已写入："
echo "  - hard : $HARD_OUTPUT"
echo "  - other: $OTHER_OUTPUT"
echo "=============================================================================="
