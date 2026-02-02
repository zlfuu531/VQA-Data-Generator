cdel_name}/ 目录下)"
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
echo "  多轮题目计分: $MULTI_ROUND_COUNT_BY_ROUNDS ($([ "$MULTI_ROUND_COUNT_BY_ROUNDS" = "true" ] && echo "按轮次计分" || echo "整题计分"))"
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

# 切换到 evaluate 目录（evaluate_py 模块的根目录）
EVAL_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$EVAL_ROOT"

python -m evaluate_py.main "${CMD_ARGS[@]}"

echo ""
echo "=============================================================================="
echo "评测完成！"
echo "=============================================================================="