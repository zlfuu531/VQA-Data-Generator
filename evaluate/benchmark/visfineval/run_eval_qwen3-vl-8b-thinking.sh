#!/bin/bash
# ==============================================================================
# VisFinEval 数据集评测脚本 - qwen3-vl-8b-thinking
# ==============================================================================
# 用途：使用 evaluate_py 框架评测 VisFinEval 数据集（sampled_3000.xlsx）
# ==============================================================================
set -eu
# 如果bash版本支持pipefail，则启用它（bash 3.0+）
if [[ "${BASH_VERSION%%.*}" -ge 3 ]] 2>/dev/null; then
    set -o pipefail
fi

# 加载通用工具函数
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
if [ -f "$PROJECT_ROOT/utils_common.sh" ]; then
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

# ==============================================================================
# 基础路径配置
# ==============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INPUT_FILE="/nfsdata-117/project/DeepEyes_Benchmark/qa_pipline12-7/evaluate/benchmark/visfineval/sampled_3000.xlsx"
OUTPUT_FILE="visfineval_sampled_3000-new.jsonl"
LOG_DIR="$SCRIPT_DIR/logs"
LOG_LEVEL="INFO"

# ==============================================================================
# 模型配置
# ==============================================================================
EVAL_MODELS="Qwen3-VL-8B-Thinking"

# ==============================================================================
# 用户画像配置
# ==============================================================================
PROFILES="expert"

# ==============================================================================
# 运行配置
# ==============================================================================
RESUME=true
LIMIT=""
USE_RANDOM=false
SEED="42"

# ==============================================================================
# 性能与并发配置
# ==============================================================================
WORKERS=40                                                 # 并发线程数
BATCH=5                                                    # 批量处理大小

# ==============================================================================
# 日志配置
# ==============================================================================
LOG_MODE="detailed"

# ==============================================================================
# 超时与重试配置
# ==============================================================================
TIMEOUT=1200
MAX_RETRIES=3
RETRY_SLEEP=1.0

# ==============================================================================
# 统计计分配置
# ==============================================================================
MULTI_ROUND_COUNT_BY_ROUNDS=true

# ==============================================================================
# 预检查
# ==============================================================================
if ! check_file_exists "$INPUT_FILE" "输入文件"; then
    exit 1
fi

mkdir -p "./outputs"
mkdir -p "$LOG_DIR"

# ==============================================================================
# 构建环境变量
# ==============================================================================
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

# ==============================================================================
# 构建命令参数
# ==============================================================================
CMD_ARGS=(
    "--input_file" "$INPUT_FILE"
    "--log_dir" "$LOG_DIR"
    "--log_level" "$LOG_LEVEL"
)

if [ -n "$OUTPUT_FILE" ]; then
    CMD_ARGS+=("--output_file" "$OUTPUT_FILE")
fi

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

# ==============================================================================
# 打印配置信息
# ==============================================================================
echo "=============================================================================="
echo "评测配置 - qwen3-vl-8b-thinking"
echo "=============================================================================="
echo "输入文件: $INPUT_FILE"
echo "输出文件: $OUTPUT_FILE (保存在 ./outputs/{profile}/{model_name}/ 目录下)"
echo "日志目录: $LOG_DIR"
echo "日志级别: $LOG_LEVEL"
echo ""
echo "模型配置:"
echo "  要评测的模型: $EVAL_MODELS"
echo ""
echo "用户画像: ${PROFILES:-全部 (beginner, retail, expert, expert_cot)}"
if [ "$RESUME" = "true" ]; then
    echo "断点续跑: ✅ 已启用"
else
    echo "断点续跑: ❌ 全新运行"
fi
echo ""
echo "并发配置:"
echo "  并发线程数: $WORKERS"
echo "  批量处理大小: $BATCH"
echo ""
echo "超时与重试配置:"
echo "  超时时间: ${TIMEOUT}s"
echo "  最大重试: $MAX_RETRIES 次"
echo "  重试延迟: ${RETRY_SLEEP}s"
echo ""
echo "其他配置:"
echo "  日志模式: $LOG_MODE"
echo "  多轮题目计分: $MULTI_ROUND_COUNT_BY_ROUNDS ($([ "$MULTI_ROUND_COUNT_BY_ROUNDS" = "true" ] && echo "按轮次计分" || echo "整题计分"))"
echo "=============================================================================="
echo ""

# ==============================================================================
# 运行评测
# ==============================================================================
echo "开始评测..."

EVAL_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$EVAL_ROOT"

python -m evaluate_py.main "${CMD_ARGS[@]}"

echo ""
echo "=============================================================================="
echo "评测完成！"
echo "=============================================================================="

