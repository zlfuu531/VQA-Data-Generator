#!/usr/bin/env python3
"""
重构 JSON/JSONL 文件中的 question_id
将 question_id 改为 {image_type}_{原id} 格式，例如：mixed_1
"""
import json
import argparse
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

# ==================== 默认配置参数 ====================
# 默认输入文件路径（如果设置为 None，则必须通过命令行参数提供）
DEFAULT_INPUT_FILE: Optional[str] = "/nfsdata-117/Project/DeepEyes_Benchmark/QA-Check/wuzhenyu/video_qa_check.json"
# DEFAULT_INPUT_FILE = None  # 取消注释此行以禁用默认路径

# 默认输出文件路径（如果设置为 None，则覆盖输入文件）
DEFAULT_OUTPUT_FILE: Optional[str] = "/nfsdata-117/Project/DeepEyes_Benchmark/QA-Check/wuzhenyu/video_qa_new_check.json"
# DEFAULT_OUTPUT_FILE = "/path/to/output.json"  # 可以设置默认输出路径


def load_json_file(file_path: Path) -> List[Dict[str, Any]]:
    """加载 JSON 文件（数组格式）"""
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    elif isinstance(data, dict) and "items" in data:
        return data["items"]
    else:
        return [data]


def load_jsonl_file(file_path: Path) -> List[Dict[str, Any]]:
    """加载 JSONL 文件（每行一个 JSON 对象）"""
    items = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
                items.append(item)
            except json.JSONDecodeError as e:
                print(f"⚠️ 警告：第 {line_num} 行 JSON 解析失败: {e}", file=sys.stderr)
                continue
    return items


def save_json_file(data: List[Dict[str, Any]], file_path: Path):
    """保存为 JSON 文件（数组格式）"""
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def save_jsonl_file(data: List[Dict[str, Any]], file_path: Path):
    """保存为 JSONL 文件（每行一个 JSON 对象）"""
    with open(file_path, 'w', encoding='utf-8') as f:
        for item in data:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')


def refactor_question_id(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    重构单个数据项的 question_id
    格式：{image_type}_{原id}
    
    Args:
        item: 原始数据项
        
    Returns:
        重构后的数据项
    """
    # 创建副本，避免修改原对象
    new_item = item.copy()
    
    # 获取 image_type 和原始 question_id
    image_type = item.get("image_type", "")
    original_id = item.get("question_id", "")
    
    # 如果 image_type 为空，使用默认值 "unknown"
    if not image_type:
        print(f"⚠️ 警告：question_id={original_id} 的 image_type 为空，使用 'unknown'", file=sys.stderr)
        image_type = "unknown"
    
    # 如果 question_id 为空，跳过
    if original_id == "" or original_id is None:
        print(f"⚠️ 警告：跳过 question_id 为空的数据项", file=sys.stderr)
        return new_item
    
    # 转换为字符串以便处理
    original_id_str = str(original_id)
    
    # 检查是否已经是重构后的格式（格式：{image_type}_{数字}）
    # 避免重复处理
    if "_" in original_id_str:
        parts = original_id_str.split("_", 1)
        if len(parts) == 2 and parts[0] == image_type:
            # 已经是正确格式，直接返回
            return new_item
        # 如果有下划线但不是 image_type 前缀，仍然处理（可能是其他格式）
    
    # 构建新的 question_id：{image_type}_{原id}
    new_question_id = f"{image_type}_{original_id_str}"
    
    # 更新 question_id
    new_item["question_id"] = new_question_id
    
    return new_item


def main():
    parser = argparse.ArgumentParser(
        description="重构 JSON/JSONL 文件中的 question_id，格式：{image_type}_{原id}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # JSON 格式文件
  python refactor_question_id.py input.json output.json
  
  # JSONL 格式文件
  python refactor_question_id.py input.jsonl output.jsonl
  
  # 自动判断格式
  python refactor_question_id.py input.jsonl -o output.jsonl
        """
    )
    
    parser.add_argument(
        "input_file",
        type=str,
        nargs='?',  # 使参数可选
        default=None,
        help=f"输入文件路径（支持 .json 或 .jsonl）{'（如果不指定，使用默认路径）' if DEFAULT_INPUT_FILE else ''}"
    )
    
    parser.add_argument(
        "-o", "--output",
        type=str,
        default=DEFAULT_OUTPUT_FILE,
        help="输出文件路径（如果不指定，则覆盖输入文件）"
    )
    
    parser.add_argument(
        "--format",
        type=str,
        choices=["auto", "json", "jsonl"],
        default="auto",
        help="输出格式（auto=根据文件扩展名自动判断，json=JSON数组，jsonl=JSONL格式）"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只预览修改，不实际写入文件"
    )
    
    args = parser.parse_args()
    
    # 解析输入文件路径（使用命令行参数或默认路径）
    input_file = args.input_file or DEFAULT_INPUT_FILE
    if not input_file:
        parser.error("必须提供输入文件路径（通过命令行参数或设置 DEFAULT_INPUT_FILE）")
    
    input_path = Path(input_file)
    if not input_path.exists():
        print(f"❌ 错误：输入文件不存在: {input_path}", file=sys.stderr)
        sys.exit(1)
    
    # 确定输出文件路径
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = input_path
    
    # 确定文件格式
    input_suffix = input_path.suffix.lower()
    if args.format == "auto":
        if input_suffix == ".jsonl":
            file_format = "jsonl"
        else:
            file_format = "json"
    else:
        file_format = args.format
    
    # 加载数据
    print(f"📖 正在读取文件: {input_path}")
    if input_suffix == ".jsonl":
        data = load_jsonl_file(input_path)
    else:
        data = load_json_file(input_path)
    
    print(f"✅ 成功加载 {len(data)} 条数据")
    
    # 重构 question_id
    print(f"🔄 正在重构 question_id...")
    refactored_data = []
    for i, item in enumerate(data):
        try:
            new_item = refactor_question_id(item)
            refactored_data.append(new_item)
        except Exception as e:
            print(f"⚠️ 警告：处理第 {i+1} 条数据时出错: {e}", file=sys.stderr)
            refactored_data.append(item)  # 保留原数据
    
    # 显示预览（前几条）
    if len(refactored_data) > 0:
        print(f"\n📋 预览（前3条）:")
        for i, item in enumerate(refactored_data[:3]):
            old_id = data[i].get("question_id", "N/A")
            new_id = item.get("question_id", "N/A")
            image_type = item.get("image_type", "N/A")
            print(f"  {i+1}. {old_id} -> {new_id} (image_type: {image_type})")
        if len(refactored_data) > 3:
            print(f"  ... (共 {len(refactored_data)} 条)")
    
    # 保存文件
    if args.dry_run:
        print(f"\n🔍 [预览模式] 不会实际写入文件")
        print(f"   如果执行，将保存到: {output_path}")
    else:
        print(f"\n💾 正在保存到: {output_path}")
        if file_format == "jsonl":
            save_jsonl_file(refactored_data, output_path)
        else:
            save_json_file(refactored_data, output_path)
        print(f"✅ 重构完成！共处理 {len(refactored_data)} 条数据")


if __name__ == "__main__":
    main()

