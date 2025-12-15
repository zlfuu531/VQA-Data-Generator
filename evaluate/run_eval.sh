#!/bin/bash
# ==============================================================================
# 评测脚本
# ==============================================================================
# 用途：运行金融领域多用户画像评测
# 说明：所有配置项都在下面，直接修改即可
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
INPUT_FILE="/home/zenglingfeng/qa_pipline12-7/output/测试问题.jsonl" # 输入文件路径（支持 .json, .jsonl 或 .csv）
OUTPUT_FILE="测试.jsonl"                            # 只需要填写输出文件名，不要填写路径（支持 .json 或 .jsonl，根据扩展名自动判断格式）
                                                           # 文件将保存在：./outputs/{profile}/{model_name}/{OUTPUT_FILE}
                                                           # 例如：eval_results.json -> ./outputs/expert/qwenvlmax/eval_results.json
                                                           # 如果为空字符串("")，则使用自动生成的带时间戳的文件名
                                                           # ⚠️ 重要：如果启用断点续传（RESUME=true），必须设置 OUTPUT_FILE，否则会报错
                                                           # 注意：输出目录固定为 ./outputs，按用户画像和模型分类组织
LOG_DIR="./evaluate_logs"                                  # 日志目录
LOG_LEVEL="INFO"                                           # 日志级别：DEBUG/INFO/WARNING/ERROR

# ==============================================================================
# 模型配置（决定评测哪些模型）
# ==============================================================================
# 说明：使用逗号分隔的字符串指定要评测的模型名称
# 模型名称必须对应 MODEL_DEFINITIONS 中的 key（在 config.py 中定义）
# 单个模型：EVAL_MODELS="qwen-vl-max"
# 多个模型：EVAL_MODELS="doubao-seed-1-6-251015,GLM-4.6V,qwen-vl-max"
EVAL_MODELS="qwen-vl-max"                    # 要评测的模型列表（逗号分隔），可以复制多个本shell，单个shell评测单个模型
# ==============================================================================
# 用户画像配置
# ==============================================================================
# 四种用户画像：
#   - beginner（金融小白）：扮演完全不懂金融的用户，用简单易懂的方式思考
#   - retail（散户投资者）：扮演有一定金融基础的散户，用专业但易懂的方式思考
#   - expert（金融专家）：扮演资深的金融专家，用深度专业的方式思考
#   - expert_cot（金融专家CoT）：扮演金融专家并使用思维链推理方法
# 使用逗号分隔的字符串指定用户画像，空字符串表示使用所有
# 单个画像：PROFILES="expert"
# 多个画像：PROFILES="beginner,retail,expert,expert_cot"

#PROFILES="expert"                                                 # 用户画像列表（逗号分隔），空字符串表示使用所有
# PROFILES="beginner,retail"                               # 示例：只评测 beginner 和 retail
PROFILES="expert"                             # 示例：对比正常专家和CoT专家

# ==============================================================================
# 运行配置
# ==============================================================================
RESUME=true                                                # 断点续跑： true(从输出文件中读取已处理的问题，跳过已完成的部分) 或 false(全新运行)
                                                           # 如果 OUTPUT_FILE 已指定，将从 ./outputs/{profile}/{model_name}/{OUTPUT_FILE} 中读取
                                                           # 如果 OUTPUT_FILE 为空，将从输出目录中查找匹配的文件
                                                           # 如果不续传且文件已存在，会自动生成 _v2、_v3 等版本号
LIMIT="8"                                                   # 限制处理数量：设置为数字（如"10"）只处理前N条数据，设置为空字符串("")处理全部数据
USE_RANDOM=false                                            # 随机选择：true(随机选择/打乱顺序) 或 false(按顺序处理)
SEED="42"                                                   # 随机种子（仅当USE_RANDOM=true时有效）

# ==============================================================================
# 性能与并发配置（预留，当前版本暂不支持并发）
# ==============================================================================
WORKERS=8                                                  # 总并发线程数
BATCH=10                                                    # 批量处理大小，对应 EVAL_BATCH_SIZE

# ==============================================================================
# 日志配置
# ==============================================================================
LOG_MODE="simple"                                           # 日志模式：simple(简化) 或 detailed(详细)

# ==============================================================================
# 超时与重试配置（具体的在config.py中定义）
# ==============================================================================
TIMEOUT=600                                                 # 单次API请求超时时间（秒），默认600秒
MAX_RETRIES=3                                               # 请求失败时的最大重试次数，默认3次
RETRY_SLEEP=1.0                                             # 请求失败后的基础重试间隔（秒），后续按指数退避，默认1秒

# ==============================================================================
# 预检查
# ==============================================================================
if ! check_file_exists "$INPUT_FILE" "输入文件"; then
    exit 1
fi

# 创建必要的目录
# 输出目录固定为 ./outputs，按用户画像和模型分类组织
mkdir -p "./outputs"
mkdir -p "$LOG_DIR"

# ==============================================================================
# 构建环境变量（传递给Python脚本）
# ==============================================================================
# 设置要评测的模型列表（已经是逗号分隔的字符串）
export EVAL_MODELS="$EVAL_MODELS"

# 设置其他配置
export EVAL_TIMEOUT="$TIMEOUT"
export EVAL_MAX_RETRIES="$MAX_RETRIES"
export EVAL_RETRY_SLEEP="$RETRY_SLEEP"
export EVAL_JUDGE_MAX_RETRIES="$MAX_RETRIES"              # 裁判模型重试次数（使用相同值）
export EVAL_JUDGE_RETRY_DELAY="$RETRY_SLEEP"              # 裁判模型重试延迟（使用相同值）
export EVAL_LIMIT="$LIMIT"
export EVAL_USE_RANDOM="$USE_RANDOM"
export EVAL_SEED="$SEED"
export EVAL_LOG_MODE="$LOG_MODE"
export EVAL_WORKERS="$WORKERS"
export EVAL_BATCH_SIZE="$BATCH"                            # 传递批量写入大小，作用于 JSON buffer 刷新

# ==============================================================================
# 构建命令参数
# ==============================================================================
CMD_ARGS=(
    "--input_file" "$INPUT_FILE"
    "--log_dir" "$LOG_DIR"
    "--log_level" "$LOG_LEVEL"
)

# 添加输出文件参数（如果指定了）
if [ -n "$OUTPUT_FILE" ]; then
    CMD_ARGS+=("--output_file" "$OUTPUT_FILE")
fi

# 添加断点续跑参数
if [ "$RESUME" = "true" ]; then
    CMD_ARGS+=("--resume")
fi

# 添加用户画像参数
if [ -n "$PROFILES" ]; then
    CMD_ARGS+=("--profiles")
    # 将逗号分隔的字符串拆分为数组
    IFS=',' read -ra PROFILE_ARRAY <<< "$PROFILES"
    for profile in "${PROFILE_ARRAY[@]}"; do
        # 去除前后空格
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
echo "评测配置"
echo "=============================================================================="
echo "输入文件: $INPUT_FILE"
if [ -n "$OUTPUT_FILE" ]; then
    echo "输出文件: $OUTPUT_FILE (保存在 ./outputs/{profile}/{model_name}/ 目录下)"
else
    echo "输出文件: 自动生成（保存在 ./outputs/ 目录下，带时间戳）"
fi
echo "日志目录: $LOG_DIR"
echo "日志级别: $LOG_LEVEL"
echo ""
echo "模型配置:"
echo "  要评测的模型: $EVAL_MODELS"
echo ""
echo "用户画像: ${PROFILES:-全部 (beginner, retail, expert, expert_cot)}"
if [ "$RESUME" = "true" ]; then
    echo "断点续跑: ✅ 已启用（将从输出文件中读取已处理的问题）"
else
    echo "断点续跑: ❌ 全新运行"
fi
if [ -n "$LIMIT" ]; then
    echo "限制数量: $LIMIT"
    echo "随机选择: $USE_RANDOM"
    if [ "$USE_RANDOM" = "true" ]; then
        echo "随机种子: $SEED"
    fi
fi
echo ""
echo "超时与重试配置:"
echo "  超时时间: ${TIMEOUT}s"
echo "  最大重试: $MAX_RETRIES 次"
echo "  重试延迟: ${RETRY_SLEEP}s"
echo ""
echo "其他配置:"
echo "  日志模式: $LOG_MODE"
if [ -n "$OUTPUT_FILE" ]; then
    echo "  输出格式: 由输出文件后缀决定 (${OUTPUT_FILE##*.})"
else
    echo "  输出格式: 默认 json（未指定输出文件名时自动生成）"
fi
echo "=============================================================================="
echo ""

# ==============================================================================
# 运行评测
# ==============================================================================
echo "开始评测..."
python main.py "${CMD_ARGS[@]}"

echo ""
echo "=============================================================================="
echo "评测完成！"
echo "=============================================================================="
