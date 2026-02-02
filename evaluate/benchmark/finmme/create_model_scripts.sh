#!/bin/bash
# ==============================================================================
# 为 config.py 中的所有模型生成评测脚本
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_FILE="$SCRIPT_DIR/run_eval_finmme.sh"

# 模型列表（从 config.py 中获取，排除裁判模型）
MODELS=(
    "doubao-seed-1-6-251015"
    "GLM-4.6V"
    "qwen-vl-max"
    "qwen3-vl-plus"
    "gpt-5.1-2025-11-13"
    "gemini-3-pro-preview"
    "grok-4-1-fast-reasoning"
    "claude-sonnet-4-5-20250929"
    "qwen3-vl-235b-a22b-thinking"
    "qwen3-vl-32b-thinking"
    "InternVL3_5-241B-A28B"
    "InternVL3_5-30B-A3B"
    "MiniCPM-V-4_5"
    "Llama-3.2-11B-Vision"
    "Qwen3-VL-8B-Thinking"
    "Qwen3-VL-8B-Instruct"
)

# 为每个模型创建脚本
for MODEL in "${MODELS[@]}"; do
    # 生成文件名（将特殊字符替换为下划线）
    SCRIPT_NAME="run_eval_${MODEL//[^a-zA-Z0-9]/_}.sh"
    SCRIPT_PATH="$SCRIPT_DIR/$SCRIPT_NAME"
    
    # 复制模板
    cp "$TEMPLATE_FILE" "$SCRIPT_PATH"
    
    # 替换模型名称（需要转义特殊字符）
    MODEL_ESCAPED=$(echo "$MODEL" | sed 's/[[\.*^$()+?{|]/\\&/g')
    sed -i "s/EVAL_MODELS=\".*\"/EVAL_MODELS=\"$MODEL_ESCAPED\"/" "$SCRIPT_PATH"
    
    # 更新注释
    sed -i "s/# 当前脚本评测的模型：.*/# 当前脚本评测的模型：$MODEL/" "$SCRIPT_PATH"
    
    # 添加执行权限
    chmod +x "$SCRIPT_PATH"
    
    echo "✅ 创建脚本: $SCRIPT_NAME"
done

echo ""
echo "=============================================================================="
echo "完成！已为 ${#MODELS[@]} 个模型创建评测脚本"
echo "=============================================================================="

