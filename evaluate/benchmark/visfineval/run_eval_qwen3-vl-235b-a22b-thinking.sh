#!/bin/bash
# ==============================================================================
# VisFinEval 数据集评测脚本 - qwen3-vl-235b-a22b-thinking
# ==============================================================================
set -eu
if [[ "${BASH_VERSION%%.*}" -ge 3 ]] 2>/dev/null; then
    set -o pipefail
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
if [ -f "$PROJECT_ROOT/utils_common.sh" ]; then
    source "$PROJECT_ROOT/utils_common.sh"
else
    print_error() { echo "❌ 错误：$1"; [ -n "${2:-}" ] && echo "   💡 建议：$2"; }
    check_file_exists() {
        [ -f "$1" ] || { print_error "找不到文件" "路径: $1"; return 1; }
    }
fi

INPUT_FILE="/home/zenglingfeng/qa_pipline12-7/evaluate/benchmark/visfineval/sampled_3000.xlsx"
OUTPUT_FILE="visfineval_sampled_3000.jsonl"
LOG_DIR="$SCRIPT_DIR/logs"
LOG_LEVEL="INFO"

EVAL_MODELS="qwen3-vl-235b-a22b-thinking"
PROFILES="expert"
RESUME=true
LIMIT=""
USE_RANDOM=false
SEED="42"
WORKERS=16                                                 # 大模型并发设置为8
BATCH=5
LOG_MODE="detailed"
TIMEOUT=1200
MAX_RETRIES=3
RETRY_SLEEP=1.0
MULTI_ROUND_COUNT_BY_ROUNDS=true

if ! check_file_exists "$INPUT_FILE" "输入文件"; then
    exit 1
fi

mkdir -p "./outputs"
mkdir -p "$LOG_DIR"

export EVAL_MODELS="$EVAL_MODELS"
export EVAL_TIMEOUT="$TIMEOUT"
export EVAL_MAX_RETRIES="$MAX_RETRIES"
export EVAL_RETRY_SLEEP="$RETRY_SLEEP"
export EVAL_JUDGE_MAX_RETRIES="$MAX_RETRIES"
export EVAL_JUDGE_RETRY_DELAY="$RETRY_SLEEP"
export EVAL_LIMIT="$LIMIT"
export EVAL_USE_RANDOM="$USE_RANDOM"
export EVAL_SEED="$SEED"
export EVAL_LOG_MODE="$LOG_MODE"
export EVAL_WORKERS="$WORKERS"
export EVAL_BATCH_SIZE="$BATCH"
export EVAL_MULTI_ROUND_COUNT_BY_ROUNDS="$MULTI_ROUND_COUNT_BY_ROUNDS"

CMD_ARGS=(
    "--input_file" "$INPUT_FILE"
    "--log_dir" "$LOG_DIR"
    "--log_level" "$LOG_LEVEL"
    "--output_file" "$OUTPUT_FILE"
)

if [ "$RESUME" = "true" ]; then
    CMD_ARGS+=("--resume")
fi

if [ -n "$PROFILES" ]; then
    CMD_ARGS+=("--profiles")
    IFS=',' read -ra PROFILE_ARRAY <<< "$PROFILES"
    for profile in "${PROFILE_ARRAY[@]}"; do
        profile=$(echo "$profile" | xargs)
        if [ -n "$profile" ]; then
            CMD_ARGS+=("$profile")
        fi
    done
fi

echo "=============================================================================="
echo "评测配置 - qwen3-vl-235b-a22b-thinking"
echo "=============================================================================="
echo "输入文件: $INPUT_FILE"
echo "输出文件: $OUTPUT_FILE"
echo "模型: $EVAL_MODELS"
echo "并发线程数: $WORKERS (大模型)"
echo "=============================================================================="
echo ""

EVAL_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$EVAL_ROOT"

python -m evaluate_py.main "${CMD_ARGS[@]}"

echo ""
echo "=============================================================================="
echo "评测完成！"
echo "=============================================================================="

