#!/usr/bin/env bash

# ==============================================================================
# 模块2：问题难度分级
# ------------------------------------------------------------------------------
# 使用方式（在项目根目录或本目录下执行）：
#   bash module2/main.sh
#
# 如需修改：
#   1. 修改「用户可配置区域」里的 INPUT_FILE / OUTPUT_DIR
#   2. 如需重新评估（生成 _v2/_v3 ...），把 RE_EVALUATE 改成 true
#   3. API 地址 / 模型名称 / API_KEY 设置见 module2/config.py 
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
    check_placeholder() {
        local value="$1"
        local var_name="$2"
        for ph in "绝对路径" "/path/to" "your-api-key"; do
            if [[ "$value" == *"$ph"* ]]; then
                print_error "${var_name} 仍为占位符" "请修改为实际值"
                return 1
            fi
        done
        return 0
    }
    check_file_exists() {
        [ -f "$1" ] || { print_error "找不到文件" "路径: $1"; return 1; }
    }
fi

######################### 用户可配置区域 #########################

# 模块2输入文件：通常是 module1 的输出（符合 module1 定义的 9 个字段）
# 支持 .json 和 .jsonl 格式
INPUT_FILE="/home/zenglingfeng/qa_pipline12-7/output/module1/测试12-17.jsonl"

# ⚠️ 重要：请将上面的 INPUT_FILE 修改为实际的文件路径！

# 模块2输出目录（会自动创建，只输入文件夹路径，不需要文件名）
OUTPUT_DIR="../output/module2/测试问题12-17"

# 输出格式：json 或 jsonl
OUTPUT_FORMAT="json"
#禁止处理一个任务时停止切换为另一个输出格式，会重新建立输出文件，不会续上一次的输出
#建议jsonl输出，查看文字和图片预览可以通过 qa_pipline copy/查看输出文件请使用.ipynb

# 是否重新评估：
#两种模式模式，都会再处理LIMIT数量后停止
#   - true  ：每次都生成一个全新的输出目录（自动在 OUTPUT_DIR 后追加 _v2/_v3/...）
#   - false ：如果已有输出目录，则读取其中已处理过的样本（按 id），只对「未处理」样本再次评估并追加进去，主要是检测原始输出目录，不包括_v2/_v3等目录的版本
RE_EVALUATE=false

# 运行细节参数
WORKERS=4         # 并发线程数
BATCH_SIZE=10      # 批量保存大小，json格式输出使用
DEBUG_MODE=true   # 是否开启调试模式（true/false），建议开

# 样本选择参数
LIMIT="4"           # 限制处理数量：设置为数字（如"10"）只处理前N个样本，设置为空字符串("")处理全部
USE_RANDOM=false     # 随机选择：true(随机选择/打乱顺序) 或 false(按顺序处理)
SEED="42"           # 随机种子（仅当USE_RANDOM=true时有效）：
                    #   - 设置为数字（如"42"）：每次运行结果相同（可复现）
                    #   - 设置为空字符串("")：每次运行结果不同（不可复现，但仍然是随机的）

######################### 内部实现（一般不改） #########################

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_ROOT}"

# 检查 INPUT_FILE 是否已修改（占位符检查）
if ! check_placeholder "$INPUT_FILE" "INPUT_FILE" "绝对路径 /path/to"; then
    print_info "请在 module2/main.sh 中修改 INPUT_FILE 变量"
    exit 1
fi

# 检查输入文件是否存在
if ! check_file_exists "$INPUT_FILE" "输入文件"; then
    exit 1
fi

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

# 输出格式参数
CMD+=(--output-format "${OUTPUT_FORMAT}")

# 运行细节参数打通到 Python
CMD+=(--workers "${WORKERS}" --batch "${BATCH_SIZE}")
if [ "${DEBUG_MODE}" = true ]; then
  CMD+=(--debug)
fi

# 样本选择参数
if [ -n "${LIMIT}" ]; then
  CMD+=(--limit "${LIMIT}")
fi

if [ "${USE_RANDOM}" = true ]; then
  CMD+=(--random)
fi

if [ -n "${SEED}" ]; then
  CMD+=(--seed "${SEED}")
fi

echo "================================================================"
echo "🚀 启动模块2评估"
echo "📂 项目根目录: ${PROJECT_ROOT}"
echo "📥 输入文件:   ${INPUT_FILE}"
echo "💾 输出目录:   ${OUTPUT_PATH}"
echo "📝 输出格式:   ${OUTPUT_FORMAT}"
echo "🔁 重新评估:   ${RE_EVALUATE}"
echo "⚙️  并发:       ${WORKERS}"
echo "📦 Batch大小:  ${BATCH_SIZE}"
echo "🐞 调试模式:   ${DEBUG_MODE}"
if [ -n "${LIMIT}" ]; then
  echo "📊 处理限制:   ${LIMIT} 个样本"
  if [ "${USE_RANDOM}" = true ]; then
    echo "🎲 选择方式:   随机选择"
    if [ -n "${SEED}" ]; then
      echo "🎲 随机种子:   ${SEED}"
    fi
  else
    echo "📊 选择方式:   按顺序选择前 ${LIMIT} 个"
  fi
else
  if [ "${USE_RANDOM}" = true ]; then
    echo "🎲 选择方式:   随机打乱顺序"
    if [ -n "${SEED}" ]; then
      echo "🎲 随机种子:   ${SEED}"
    fi
  else
    echo "📊 处理限制:   ♾️  无限制，处理全部"
  fi
fi
echo "================================================================"
echo

"${CMD[@]}"

echo
echo "✅ 模块2评估完成。"
echo "   - 等级结果 & 汇总文件夹: ${OUTPUT_PATH}/ (内含 L1-L4.${OUTPUT_FORMAT} + summary.json)"


