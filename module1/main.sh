#!/bin/bash

# ================= 🔧 基础路径配置 =================
PY_SCRIPT="./qa_make.py"
INPUT_FILE="输入路径/input.json"
OUTPUT_FILE="../output/module1/qa_test.json"
LOG_DIR="../module1_logs"  
# ================= 🤖 模型与API配置 =================
API_BASE="http://ip:port/v1"
API_KEY="EMPTY"
MODEL="Qwen3-VL-235B"

# ================= 🎛️ 生成参数 =================
IMAGE_TYPE="all"          # 图片类型: pure_image, pure_text, mixed, splice，all
QUESTION_TYPE="essay"       # 问题类型: single_choice, multiple_choice, true_false, essay问答题, multi_round_single_choice, multi_round_essay
NUM=2                       # 每张图片生成几个问题
ROUNDS=2                    # 多轮对话的轮数（仅用于多轮对话题型）
TEMP=0.7                    # 温度参数
TOKENS=8192                 # 最大Token数

# ================= 🚀 性能配置 =================
WORKERS=8                  # 并发线程数
BATCH=8                    # json批量写入大小

# ================= 🛑 其他配置 =================
RESUME=false                # 是否断点续传 (true/false)
LIMIT="10"                   # 限制处理的图片数量，设置为空字符串 "" 则处理全部
ENABLE_THINKING=false       # 是否启用思考模式 (true/false)，启用后会提取 reasoning_content

# ================= 执行 =================
echo "========================================================"
echo "🚀 启动参数确认"
echo "--------------------------------------------------------"
echo "📂 输入: $INPUT_FILE"
echo "💾 输出: $OUTPUT_FILE"
echo "🖼️  图片类型: $IMAGE_TYPE"
echo "❓ 问题类型: $QUESTION_TYPE"
echo "🔢 数量: 每张图 $NUM 题"
if [[ "$QUESTION_TYPE" == *"multi_round"* ]]; then
    echo "🔄 轮数: $ROUNDS 轮"
fi
echo "========================================================"

# 构建命令
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
    --temp $TEMP \
    --tokens $TOKENS \
    --workers $WORKERS \
    --batch $BATCH \
    --log_dir '$LOG_DIR'"

# 添加可选参数
if [ "$RESUME" = true ]; then
    CMD="$CMD --resume"
    echo "🔍 模式: [断点续传]"
else
    echo "🆕 模式: [全新运行]"
fi

if [ "$ENABLE_THINKING" = true ]; then
    CMD="$CMD --enable_thinking"
    echo "🧠 思考模式: [已启用]"
fi

if [ ! -z "$LIMIT" ]; then
    CMD="$CMD --limit $LIMIT"
    echo "✂️  限制: [仅处理前 $LIMIT 张图片]"
else
    echo "♾️  限制: [无限制，跑完全部数据]"
fi

echo ""
eval $CMD
