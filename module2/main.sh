#!/usr/bin/env bash

# ==============================================================================
# 模块2：模型评估一键脚本
# ------------------------------------------------------------------------------
# 使用方式（在项目根目录或本目录下执行）：
#   bash module2/main.sh
#
# 如需修改：
#   1. 修改「用户可配置区域」里的 INPUT_FILE / OUTPUT_DIR
#   2. 如需重新评估（生成 _v2/_v3 ...），把 RE_EVALUATE 改成 true
#   3. API 地址 / 模型名称 / API_KEY 固定写在 module2/config.py 里
# ==============================================================================

set -euo pipefail

######################### 用户可配置区域 #########################

# 模块2输入文件：通常是 module1 的输出（符合 module1 定义的 9 个字段）

INPUT_FILE="你的地址/qa_result.json"
# 模块2输出目录（会自动创建）
OUTPUT_DIR="../output/module2/qa_qwen235b-nothink-essay"


# 是否重新评估：
#   - true  ：每次都生成一个全新的输出目录（自动在 OUTPUT_DIR 后追加 _v2/_v3/...）
#   - false ：如果已有输出目录，则读取其中已处理过的样本（按 id），只对「未处理」样本再次评估并追加进去，主要是检测原始输出目录，不包括_v2/_v3等目录的版本
RE_EVALUATE=true

# 运行细节参数
WORKERS=10         # 并发线程数
BATCH_SIZE=10      # 批量保存大小
DEBUG_MODE=true   # 是否开启调试模式（true/false），建议开

######################### 内部实现（一般不改） #########################

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_ROOT}"

# 加载根目录下的 .env（如果存在），用于注入 API Key 等环境变量
if [ -f ".env" ]; then
  # 让 .env 中的每一行 KEY=VALUE 都自动成为环境变量
  set -a
  # shell 在非交互模式下也能正确加载
  . ".env"
  set +a
fi

# 根据 RE_EVALUATE 决定最终的输出目录：
# - true  ：如果已存在 OUTPUT_DIR，则依次尝试 OUTPUT_DIR_v2, OUTPUT_DIR_v3, ... 直到找到一个不存在的目录
# - false ：直接使用 OUTPUT_DIR，本身是否存在由 Python 内部决定（无则新建，有则做增量）
TARGET_OUTPUT_DIR="${OUTPUT_DIR}"
if [ "${RE_EVALUATE}" = true ]; then
  base_dir="$(dirname "${OUTPUT_DIR}")"
  base_name="$(basename "${OUTPUT_DIR}")"

  if [ -d "${OUTPUT_DIR}" ]; then
    suffix=2
    while [ -d "${base_dir}/${base_name}_v${suffix}" ]; do
      suffix=$((suffix + 1))
    done
    TARGET_OUTPUT_DIR="${base_dir}/${base_name}_v${suffix}"
  fi
fi

mkdir -p "${TARGET_OUTPUT_DIR}"
OUTPUT_PATH="${TARGET_OUTPUT_DIR}"

CMD=(python -m module2.main --input "${INPUT_FILE}" --output "${OUTPUT_PATH}")

if [ "${RE_EVALUATE}" = true ]; then
  CMD+=(--re)
fi

# 运行细节参数打通到 Python
CMD+=(--workers "${WORKERS}" --batch "${BATCH_SIZE}")
if [ "${DEBUG_MODE}" = true ]; then
  CMD+=(--debug)
fi

echo "================================================================"
echo "🚀 启动模块2评估"
echo "📂 项目根目录: ${PROJECT_ROOT}"
echo "📥 输入文件:   ${INPUT_FILE}"
echo "💾 输出基名:   ${OUTPUT_PATH} (仅用于推导输出文件夹名)"
echo "🔁 重新评估:   ${RE_EVALUATE}"
echo "⚙️  并发:       ${WORKERS}"
echo "📦 Batch大小:  ${BATCH_SIZE}"
echo "🐞 调试模式:   ${DEBUG_MODE}"
echo "================================================================"
echo

"${CMD[@]}"

echo
echo "✅ 模块2评估完成。"
RESULT_PARENT_DIR="$(dirname "${OUTPUT_PATH}")"
RESULT_BASENAME="$(basename "${OUTPUT_PATH}")"
if [[ "${RESULT_BASENAME}" == *.* ]]; then
  RESULT_NAME_PART="${RESULT_BASENAME%.*}"
else
  RESULT_NAME_PART="${RESULT_BASENAME}"
fi
RESULT_DIR="${RESULT_PARENT_DIR}/${RESULT_NAME_PART}"
echo "   - 等级结果 & 汇总文件夹: ${RESULT_DIR}/ (内含 L1-L4.json + error.json + summary.json)"


