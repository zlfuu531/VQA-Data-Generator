#!/bin/bash
# ==============================================================================
# FinMME 评测示例脚本
# 展示如何使用不同的配置运行评测
# ==============================================================================

cd "$(dirname "$0")"

echo "=============================================================================="
echo "FinMME 评测示例"
echo "=============================================================================="
echo ""

# 示例 1: 基本用法
echo "示例 1: 基本用法（使用默认配置）"
echo "export EVAL_MODELS=\"qwen3-vl-32b-thinking\""
echo "export PROFILES=\"expert\""
echo "./run_eval_finmme.sh"
echo ""

# 示例 2: 多模型评测
echo "示例 2: 评测多个模型"
echo "export EVAL_MODELS=\"qwen3-vl-32b-thinking,InternVL3_5-30B-A3B\""
echo "export PROFILES=\"expert\""
echo "./run_eval_finmme.sh"
echo ""

# 示例 3: 多用户画像
echo "示例 3: 评测多个用户画像"
echo "export EVAL_MODELS=\"qwen3-vl-32b-thinking\""
echo "export PROFILES=\"expert,retail,beginner\""
echo "./run_eval_finmme.sh"
echo ""

# 示例 4: 测试模式（限制数量）
echo "示例 4: 测试模式（限制 100 条）"
echo "export EVAL_MODELS=\"qwen3-vl-32b-thinking\""
echo "export PROFILES=\"expert\""
echo "export LIMIT=\"100\""
echo "./run_eval_finmme.sh"
echo ""

# 示例 5: 完整配置
echo "示例 5: 完整配置示例"
cat << 'EOF'
export EVAL_MODELS="qwen3-vl-32b-thinking"
export PROFILES="expert"
export LIMIT=""
export WORKERS=24
export LOG_LEVEL="INFO"
export RESUME="true"
./run_eval_finmme.sh
EOF

echo ""
echo "=============================================================================="
echo "注意："
echo "1. 首次运行会自动转换数据（可能需要一些时间）"
echo "2. 转换后的数据保存在: finmme_converted.jsonl"
echo "3. 评测结果保存在: outputs/{profile}/{model_name}/finmme_eval_results.jsonl"
echo "4. 日志保存在: logs/"
echo "=============================================================================="

