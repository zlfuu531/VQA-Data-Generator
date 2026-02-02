#!/bin/bash
# ==============================================================================
# 通用工具函数 - 统一错误提示格式
# ==============================================================================
# 使用方式：在脚本开头添加：source "$(dirname "$0")/../utils_common.sh"
# ==============================================================================

# 颜色定义（如果终端支持）
if [ -t 1 ]; then
    RED='\033[91m'
    GREEN='\033[92m'
    YELLOW='\033[93m'
    BLUE='\033[94m'
    CYAN='\033[96m'
    RESET='\033[0m'
    BOLD='\033[1m'
else
    RED=''
    GREEN=''
    YELLOW=''
    BLUE=''
    CYAN=''
    RESET=''
    BOLD=''
fi

# ==============================================================================
# 统一错误提示函数
# ==============================================================================

print_error() {
    # 打印错误信息
    # 用法: print_error "错误信息" ["建议信息"]
    local message="$1"
    local suggestion="${2:-}"
    
    echo -e "${RED}❌ 错误：${message}${RESET}"
    if [ -n "$suggestion" ]; then
        echo -e "   ${YELLOW}💡 建议：${suggestion}${RESET}"
    fi
}

print_warning() {
    # 打印警告信息
    # 用法: print_warning "警告信息" ["建议信息"]
    local message="$1"
    local suggestion="${2:-}"
    
    echo -e "${YELLOW}⚠️  警告：${message}${RESET}"
    if [ -n "$suggestion" ]; then
        echo -e "   ${YELLOW}💡 建议：${suggestion}${RESET}"
    fi
}

print_success() {
    # 打印成功信息
    # 用法: print_success "成功信息"
    local message="$1"
    echo -e "${GREEN}✅ ${message}${RESET}"
}

print_info() {
    # 打印信息
    # 用法: print_info "信息"
    local message="$1"
    echo -e "${CYAN}ℹ️  ${message}${RESET}"
}

print_section() {
    # 打印章节标题
    # 用法: print_section "章节标题"
    local title="$1"
    echo ""
    echo -e "${BOLD}${BLUE}=============================================================================="
    echo -e "${title}"
    echo -e "==============================================================================${RESET}"
    echo ""
}

# ==============================================================================
# 文件路径检查函数
# ==============================================================================

check_file_exists() {
    # 检查文件是否存在
    # 用法: check_file_exists "文件路径" "文件描述"
    local file_path="$1"
    local file_desc="${2:-文件}"
    
    if [ ! -f "$file_path" ]; then
        print_error "找不到${file_desc}" "请检查路径是否正确: $file_path"
        return 1
    fi
    return 0
}

check_directory_exists() {
    # 检查目录是否存在，不存在则创建
    # 用法: check_directory_exists "目录路径" "目录描述" [create]
    local dir_path="$1"
    local dir_desc="${2:-目录}"
    local create="${3:-false}"
    
    if [ ! -d "$dir_path" ]; then
        if [ "$create" = "true" ]; then
            mkdir -p "$dir_path" 2>/dev/null
            if [ $? -eq 0 ]; then
                print_success "已创建${dir_desc}: $dir_path"
                return 0
            else
                print_error "无法创建${dir_desc}" "请检查权限: $dir_path"
                return 1
            fi
        else
            print_error "${dir_desc}不存在" "请检查路径是否正确: $dir_path"
            return 1
        fi
    fi
    return 0
}

check_file_readable() {
    # 检查文件是否可读
    # 用法: check_file_readable "文件路径" "文件描述"
    local file_path="$1"
    local file_desc="${2:-文件}"
    
    if [ ! -r "$file_path" ]; then
        print_error "${file_desc}无读取权限" "请检查文件权限: $file_path"
        return 1
    fi
    return 0
}

check_directory_writable() {
    # 检查目录是否可写
    # 用法: check_directory_writable "目录路径" "目录描述"
    local dir_path="$1"
    local dir_desc="${2:-目录}"
    
    if [ ! -w "$dir_path" ]; then
        print_error "${dir_desc}无写入权限" "请检查目录权限: $dir_path"
        return 1
    fi
    return 0
}

# ==============================================================================
# 配置验证函数
# ==============================================================================

check_placeholder() {
    # 检查变量是否为占位符
    # 用法: check_placeholder "变量值" "变量名" ["占位符列表"]
    local value="$1"
    local var_name="$2"
    local placeholders="${3:-绝对路径 /path/to your-api-key-here your_api_key}"
    
    for placeholder in $placeholders; do
        if [[ "$value" == *"$placeholder"* ]]; then
            print_error "${var_name} 仍为占位符" "请修改为实际值: $value"
            return 1
        fi
    done
    return 0
}

check_api_key() {
    # 检查 API Key 是否配置
    # 用法: check_api_key "API_KEY值" "API_KEY名称"
    local api_key="$1"
    local key_name="${2:-API Key}"
    
    if [ -z "$api_key" ] || [ "$api_key" = "your-api-key-here" ] || [ "$api_key" = "" ]; then
        print_error "${key_name} 未设置或使用默认值" "请在配置文件中设置实际的 API Key"
        return 1
    fi
    
    # 基本格式检查
    if [ ${#api_key} -lt 10 ]; then
        print_warning "${key_name} 长度过短" "可能配置错误，请检查"
        return 1
    fi
    
    return 0
}

