#!/bin/bash
# ==============================================================================
# Module1 GitHub Actions 模板脚本
# ==============================================================================
# 用途：用于 GitHub Actions 或其他 CI/CD 环境运行模块1
# 说明：所有配置项都在下面，直接修改即可
# ==============================================================================
set -euo pipefail

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
    
    # 定义检查函数
    check_api_key() {
        local key="$1"
        local name="${2:-API_KEY}"
        if [ -z "$key" ] || [ "$key" = "your_api_key_here" ] || [ "$key" = "sk-xxx" ]; then
            print_error "$name 未设置或使用默认值" "请在脚本中修改 $name 变量"
            return 1
        fi
        return 0
    }
    
    check_file_exists() {
        local file="$1"
        local name="${2:-文件}"
        if [ ! -f "$file" ]; then
            print_error "$name 不存在: $file"
            return 1
        fi
        return 0
    }
fi
# ==============================================================================
# 基础路径配置
# ==============================================================================
PY_SCRIPT="./qa_make.py"
#INPUT_FILE="/path/to/input.json"                        # 输入文件路径（支持 .json 或 .jsonl）
INPUT_FILE="/nfsdata-117/Project/DeepEyes_Benchmark/dataoutput_classified/mixed_多选.json"
OUTPUT_FILE="../output/module1/output.jsonl"             # 输出文件路径（支持 .json 或 .jsonl，根据扩展名自动判断格式）
LOG_DIR="../module1_logs"                                # 日志目录
# 格式说明：
#   - .json 格式：标准JSON数组，批量保存，需要batch参数控制（小批量测试可用）
#   - .jsonl 格式：逐行追加，无需读取整个文件，batch参数仅用于刷新频率（推荐大数据量使用）
# ==============================================================================
# 模型与API配置
# ==============================================================================
API_BASE=""  # API地址
API_KEY=""                            # API密钥
MODEL=""                                   # 模型名称
# ==============================================================================
# 题目生成参数
# ==============================================================================
IMAGE_TYPE="all"                                        # 图片类型：pure_image/pure_text/mixed/splice/stacked/all，新加了stacked重叠类型
QUESTION_TYPE="essay"                                   # 问题类型：single_choice/multiple_choice/true_false/essay/multi_round_single_choice/multi_round_essay
NUM=1                                                   # 每张图片生成几个问题（建议1-3）
ROUNDS=3                                                # 多轮对话轮数（仅用于多轮对话题型，如multi_round_single_choice/multi_round_essay）
# ==============================================================================
# 模型生成参数，如需更改更详细参数，可在qa_make.py中修改
# ==============================================================================
#TEMP=0.7                                                # 温度参数 (可选，不设置即使用模型默认温度)
TOKENS=10000                                             # 最大输出Token数（建议4096-8192）
# ==============================================================================
# 性能与并发配置
# ==============================================================================
WORKERS=10                                               # 并发线程数（根据API限流调整，建议2-10）
BATCH=10                                                 # 批量写入大小（建议10-50）
# Batch参数说明：
#   - JSON格式：控制批量保存大小，影响内存和性能，建议10-50
#   - JSONL格式：仅用于控制刷新频率，不影响写入性能（因为逐行追加，无需读取整个文件）
#   提示：如果输出文件使用.jsonl扩展名，batch参数可以设置较小值（如10）或保持默认
# ==============================================================================
# 日志配置
# ==============================================================================
LOG_MODE="detailed"                                       
# 日志模式：simple(简化，只记录省略的输出输入+token数) 或 detailed(详细，记录完整响应)
# ==============================================================================
# 运行配置
# ==============================================================================
RESUME=true                                            # 断点续传：true(从输出文件中读取已处理的图片，跳过已完成的部分) 或 false(全新运行，生成_v2版本)
LIMIT="10"                                                # 限制处理数量：设置为数字（如"10"）只处理前N张图片，设置为空字符串("")处理全部图片
USE_RANDOM=true                                        # 随机选择：true(随机选择/打乱顺序) 或 false(按顺序处理)
SEED="42"                                                 # 随机种子（仅当USE_RANDOM=true时有效）：
                                                        #   - 设置为数字（如"42"）：每次运行结果相同（可复现）
                                                        #   - 设置为空字符串("")：每次运行结果不同（不可复现，但仍然是随机的）
ENABLE_THINKING=false                                   # 思考模式：true(启用思考模式，会提取模型的reasoning_content并合并到qa_make_process) 或 false(不启用)
NO_PROCESS=true                   # 不生成解题过程：true(不生成qa_make_process字段) 或 false(生成qa_make_process字段)
# ==============================================================================
# 超时与重试配置
# ==============================================================================
TIMEOUT=1000.0                                          # 单次API请求超时时间（秒），默认1000秒
MAX_RETRIES=3                                           # 请求失败时的最大重试次数，默认3次
RETRY_SLEEP=1.0                                         # 请求失败后的基础重试间隔（秒），后续按指数退避，默认1秒
# ==============================================================================
# 预检查
# ==============================================================================
if [ ! -f "$PY_SCRIPT" ]; then
    print_error "找不到Python脚本 $PY_SCRIPT" "请确保在 module1 目录下执行此脚本"
    exit 1
fi

if ! check_api_key "$API_KEY" "API_KEY"; then
    print_info "请在脚本中修改 API_KEY 变量，或在 GitHub Actions 中通过 Secrets 设置"
    exit 1
fi

if ! check_file_exists "$INPUT_FILE" "输入文件"; then
    exit 1
fi

# 创建必要的目录
mkdir -p "$LOG_DIR"
OUTPUT_DIR=$(dirname "$OUTPUT_FILE")
mkdir -p "$OUTPUT_DIR"

# ==============================================================================
# 构建命令
# ==============================================================================
CMD="python $PY_SCRIPT \
    --input '$INPUT_FILE' \
    --output '$OUTPUT_FILE' \
    --image_type '$IMAGE_TYPE' \
    --question_type '$QUESTION_TYPE' \
    --num $NUM \
    --rounds $ROUNDS \
    --api_base '$API_BASE' \
    --api_key '$API_KEY' \
    --model '$MODEL' \
    --tokens $TOKENS \
    --workers $WORKERS \
    --batch $BATCH \
    --timeout $TIMEOUT \
    --retries $MAX_RETRIES \
    --retry_sleep $RETRY_SLEEP \
    --log_dir '$LOG_DIR' \
    --log_mode '$LOG_MODE'"

# 添加可选参数
if [ "$RESUME" = true ]; then
    CMD="$CMD --resume"
fi

if [ "$ENABLE_THINKING" = true ]; then
    CMD="$CMD --enable_thinking"
fi

if [ "$NO_PROCESS" = true ]; then
    CMD="$CMD --no_process"
fi

if [ -n "$LIMIT" ]; then
    CMD="$CMD --limit $LIMIT"
fi

# 可选温度参数：仅当填写时才传递，避免覆盖模型默认温度
TEMP_DISPLAY="(未设置，使用模型默认)"
if [ -n "${TEMP:-}" ]; then
    CMD="$CMD --temp $TEMP"
    TEMP_DISPLAY="$TEMP"
fi

if [ "$USE_RANDOM" = true ]; then
    CMD="$CMD --random"
fi

if [ -n "$SEED" ]; then
    CMD="$CMD --seed $SEED"
fi

# ==============================================================================
# 显示配置信息
# ==============================================================================
echo "========================================================================"
echo "🚀 Module1 GitHub Actions 运行"
echo "========================================================================"
echo ""
echo "📂 [文件配置]"
echo "   输入文件: $INPUT_FILE"
echo "   输出文件: $OUTPUT_FILE"
echo "   日志目录: $LOG_DIR"
echo ""
echo "🤖 [模型配置]"
echo "   API地址: $API_BASE"
echo "   模型名称: $MODEL"
echo "   温度参数: $TEMP_DISPLAY"
echo "   最大Token: $TOKENS"
echo ""
echo "🎛️  [题目配置]"
echo "   图片类型: $IMAGE_TYPE"
echo "   问题类型: $QUESTION_TYPE"
echo "   每图题数: $NUM 题"
if [[ "$QUESTION_TYPE" == *"multi_round"* ]]; then
    echo "   对话轮数: $ROUNDS 轮"
fi
echo ""
echo "⚙️  [性能配置]"
echo "   并发线程: $WORKERS"
echo "   批量写入: $BATCH"
if [[ "$OUTPUT_FILE" == *.jsonl ]]; then
    echo "   输出格式: JSONL（逐行追加，batch参数仅用于刷新频率）"
else
    echo "   输出格式: JSON（批量保存，batch参数影响性能）"
fi
echo "   请求超时: ${TIMEOUT}秒"
echo "   最大重试: ${MAX_RETRIES}次"
echo ""
echo "🛠️  [运行配置]"
if [ "$RESUME" = true ]; then
    echo "   断点续传: ✅ 已启用"
else
    echo "   断点续传: ❌ 全新运行（会生成_v2版本）"
fi

if [ "$ENABLE_THINKING" = true ]; then
    echo "   思考模式: ✅ 已启用（会提取reasoning_content）"
else
    echo "   思考模式: ❌ 未启用"
fi

if [ "$NO_PROCESS" = true ]; then
    echo "   解题过程: ❌ 不生成（只生成问题、选项和答案）"
else
    echo "   解题过程: ✅ 生成（包含qa_make_process字段）"
fi

if [ -n "$LIMIT" ]; then
    echo "   处理限制: ⚠️  ${LIMIT} 张图片"
    if [ "$USE_RANDOM" = true ]; then
        echo "   选择方式: 🎲 随机选择"
        if [ -n "$SEED" ]; then
            echo "   随机种子: 🎲 ${SEED}"
        fi
    else
        echo "   选择方式: 📊 按顺序选择前 ${LIMIT} 张"
    fi
else
    if [ "$USE_RANDOM" = true ]; then
        echo "   处理限制: ♾️  无限制，处理全部数据"
        echo "   选择方式: 🎲 随机打乱顺序"
        if [ -n "$SEED" ]; then
            echo "   随机种子: 🎲 ${SEED}"
        fi
    else
        echo "   处理限制: ♾️  无限制，处理全部数据"
    fi
fi
echo ""
echo "========================================================================"
echo "🎬 开始执行..."
echo "========================================================================"
echo ""

# ==============================================================================
# 执行命令
# ==============================================================================
eval $CMD

# ==============================================================================
# 执行完成
# ==============================================================================
echo ""
echo "========================================================================"
echo "✅ 执行完成！"
echo "========================================================================"
echo ""
echo "📁 输出文件: $OUTPUT_FILE"
if [ -f "$OUTPUT_FILE" ]; then
    FILE_SIZE=$(du -h "$OUTPUT_FILE" | cut -f1)
    echo "   文件大小: $FILE_SIZE"
fi
echo ""
echo "📝 日志目录: $LOG_DIR"
echo ""

