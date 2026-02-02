#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FinMME 数据集转换脚本
从本地数据集目录加载 FinMME 数据，转换为 evaluate_py 评测框架需要的标准格式
"""

# 在导入任何库之前设置离线模式环境变量，避免网络请求
import os
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["HF_DATASETS_OFFLINE"] = "1"

import json
import argparse
import logging
import re
from pathlib import Path
from typing import List, Dict, Any, Iterator, Optional
from PIL import Image

try:
    from datasets import load_dataset, DownloadMode
    HAS_DATASETS = True
except ImportError:
    HAS_DATASETS = False
    DownloadMode = None
    print("警告: datasets 库未安装，无法加载数据。请安装: pip install datasets")

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 默认本地数据集目录
DEFAULT_LOCAL_DATA_DIR = "/nfsdata-117/project/finvlr1/Benchmark/FinMME_data"


def save_image_to_local(image: Image.Image, image_dir: Path, image_id: str) -> Optional[str]:
    """
    将 PIL Image 对象保存到本地文件（如果文件已存在则跳过）
    
    Args:
        image: PIL Image 对象
        image_dir: 图片保存目录
        image_id: 图片ID
        
    Returns:
        保存后的图片路径（绝对路径），如果文件已存在则返回现有路径
    """
    # 创建图片保存目录
    image_dir = Path(image_dir)
    image_dir.mkdir(parents=True, exist_ok=True)
    
    # 清理 image_id 中的特殊字符，确保文件名安全
    safe_image_id = str(image_id).replace("/", "_").replace("\\", "_")
    
    # 保存图片
    image_path = image_dir / f"{safe_image_id}.png"
    
    # 如果图片已存在，直接返回现有路径
    if image_path.exists():
        logger.debug(f"图片已存在，跳过保存: {image_path}")
        return str(image_path.absolute())
    
    # 确保图片是 RGB 模式（如果不是，转换为 RGB）
    save_image = image
    if image.mode in ('RGBA', 'LA', 'P'):
        # 创建白色背景
        background = Image.new('RGB', image.size, (255, 255, 255))
        if image.mode == 'P':
            save_image = image.convert('RGBA')
        else:
            save_image = image
        background.paste(save_image, mask=save_image.split()[-1] if save_image.mode == 'RGBA' else None)
        save_image = background
    elif image.mode != 'RGB':
        save_image = image.convert('RGB')
    
    save_image.save(image_path, "PNG")
    
    # 返回绝对路径
    return str(image_path.absolute())


def parse_options_string(options_str: str) -> Optional[Dict[str, str]]:
    """
    解析 FinMME 选项字符串为字典格式
    
    FinMME 的 options 格式示例：
    "A: 3QFY22 to 3QFY23\nB: 2QFY20 to 2QFY21\nC: 4QFY23 to 1QFY24\nD: 1QFY22 to 4QFY22"
    或
    "A: 16% B: 20% C: 11% D: 15%"
    
    Args:
        options_str: 选项字符串
        
    Returns:
        字典格式的选项，如 {"A": "3QFY22 to 3QFY23", "B": "2QFY20 to 2QFY21", ...}
        如果解析失败则返回 None
    """
    if not options_str or not isinstance(options_str, str):
        return None
    
    options_str = options_str.strip()
    if not options_str:
        return None
    
    options_dict = {}
    
    # 方法1：先尝试按行分割（支持 \n 或 \r\n）
    lines = options_str.replace('\r\n', '\n').split('\n')
    has_newline = len(lines) > 1
    
    if has_newline:
        # 如果有换行符，按行处理
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 匹配 "A: xxx" 或 "A:xxx" 格式
            match = re.match(r'^([A-Z])\s*:\s*(.+)$', line)
            if match:
                key = match.group(1)
                value = match.group(2).strip()
                if key and value:
                    options_dict[key] = value
    else:
        # 方法2：没有换行符，使用正则表达式匹配所有选项
        # 匹配 "A: xxx" 格式，其中 xxx 可能包含空格，直到遇到下一个 "B: " 或字符串结束
        pattern = r'([A-Z])\s*:\s*([^A-Z]*(?:\s+[^A-Z]+)*?)(?=\s+[A-Z]\s*:|$)'
        matches = re.finditer(pattern, options_str)
        for match in matches:
            key = match.group(1)
            value = match.group(2).strip()
            if key and value:
                options_dict[key] = value
    
    return options_dict if options_dict else None


def map_question_type(finmme_type: str) -> str:
    """
    将 FinMME 的 question_type 映射到 evaluate_py 需要的中文题型
    
    Args:
        finmme_type: FinMME 的 question_type（如 "single_choice", "multiple_choice", "numerical"）
        
    Returns:
        中文题型名称
    """
    mapping = {
        "single_choice": "单选题",
        "multiple_choice": "多选题",
        "numerical": "问答题",  # 数值题当作问答题处理
    }
    return mapping.get(finmme_type, finmme_type)  # 如果没有映射，返回原值


def convert_finmme_item(item: Dict[str, Any], image_dir: Optional[Path] = None,
                       save_images: bool = True) -> Optional[Dict[str, Any]]:
    """
    将单个 FinMME 数据项转换为 evaluate_py 标准格式
    
    核心字段映射：
    - id/idx -> question_id
    - image -> image_path (保存到本地)
    - question_text -> question
    - question_type -> question_type (英文映射到中文)
    - options -> options (字符串转换为字典)
    - answer -> answer
    
    Args:
        item: FinMME 数据项（从 datasets 加载的原始数据）
        image_dir: 图片保存目录（如果为 None，则不保存图片）
        save_images: 是否将图片保存到本地
        
    Returns:
        转换后的标准格式数据项
    """
    converted = {}
    
    # 1. question_id: 使用 id 或 idx（优先使用 id，如果 id 不存在则使用 idx）
    # 注意：id 可能为 0，需要正确处理
    question_id = item.get("id")
    if question_id is None:
        question_id = item.get("idx")
    if question_id is None:
        question_id = ""
    converted["question_id"] = str(question_id) if question_id != "" else ""
    
    # 2. image_id: 使用 question_id 作为 image_id（图片和问题一一对应）
    converted["image_id"] = converted["question_id"]
    
    # 3. question: 从 question_text 获取
    converted["question"] = str(item.get("question_text", ""))
    
    # 4. question_type: 从英文映射到中文
    finmme_question_type = str(item.get("question_type", ""))
    converted["question_type"] = map_question_type(finmme_question_type)
    
    # 5. answer: 直接使用
    converted["answer"] = str(item.get("answer", ""))
    
    # 6. options: 将字符串转换为字典格式
    options = item.get("options")
    if options is None:
        converted["options"] = None
    elif isinstance(options, dict):
        # 如果已经是字典，直接使用
        converted["options"] = options
    elif isinstance(options, str):
        # 如果是字符串，解析为字典
        converted["options"] = parse_options_string(options)
    else:
        converted["options"] = None
    
    # 7. image_path: 处理图片
    if "image" in item and item["image"] is not None:
        image = item["image"]
        if isinstance(image, Image.Image):
            if save_images and image_dir:
                image_id = converted.get("image_id", question_id)
                try:
                    # 如果图片已存在，直接返回现有路径；否则保存图片
                    image_path = save_image_to_local(image, image_dir, image_id)
                    converted["image_path"] = image_path
                except Exception as e:
                    logger.warning(f"保存图片失败 (image_id: {image_id}): {e}")
                    converted["image_path"] = ""
            else:
                # 如果不保存图片，但需要设置路径（用于后续检查图片是否存在）
                if image_dir:
                    image_id = converted.get("image_id", question_id)
                    safe_image_id = str(image_id).replace("/", "_").replace("\\", "_")
                    image_path = image_dir / f"{safe_image_id}.png"
                    if image_path.exists():
                        converted["image_path"] = str(image_path.absolute())
                    else:
                        converted["image_path"] = ""
                else:
                    converted["image_path"] = ""
        else:
            converted["image_path"] = ""
    else:
        converted["image_path"] = ""
    
    # 8. image_type: 设置为空（FinMME 数据集中没有此字段）
    converted["image_type"] = ""
    
    # 9. 保留其他所有字段（不参与评测，但保留用于统计等）
    for key, value in item.items():
        if key not in ["id", "idx", "question_text", "question_type", "options", "answer", "image"]:
            converted[key] = value
    
    # 验证必需字段：如果问题和答案缺失，返回 None（将被跳过）
    if not converted.get("question") or not converted.get("question", "").strip():
        logger.warning(f"数据项 {question_id} 缺少必需字段 question，已跳过")
        return None
    
    if not converted.get("answer") or not converted.get("answer", "").strip():
        logger.warning(f"数据项 {question_id} 缺少必需字段 answer，已跳过")
        return None
    
    # question_id 可以为空，但如果为空会使用索引
    if not converted.get("question_id"):
        logger.debug(f"数据项 question_id 为空，将使用索引")
    
    return converted


def load_finmme_from_local(local_dir: str, dataset_name: str = "luojunyu/FinMME", 
                           split: str = "train") -> Iterator[Dict[str, Any]]:
    """
    从本地目录加载 FinMME 数据集（离线模式，不连接网络）
    
    Args:
        local_dir: 本地数据集目录路径
        dataset_name: 数据集名称（用于 load_dataset）
        split: 数据集分割（train/test）
        
    Yields:
        FinMME 数据项
    """
    if not HAS_DATASETS:
        raise ImportError("datasets 库未安装，无法加载数据")
    
    logger.info(f"从本地目录加载数据集: {local_dir}")
    logger.info(f"数据集名称: {dataset_name}, 分割: {split}")
    
    try:
        # 从本地缓存加载（不使用 streaming，直接从本地加载）
        # 环境变量已在文件开头设置，这里直接使用离线模式参数
        download_mode = DownloadMode.REUSE_CACHE_IF_EXISTS if DownloadMode else "reuse_cache_if_exists"
        dataset = load_dataset(
            dataset_name,
            split=split,
            cache_dir=local_dir,
            streaming=False,  # 不使用 streaming，直接从本地加载
            trust_remote_code=True,
            download_mode=download_mode  # 如果缓存存在则复用，不下载
        )
        logger.info(f"成功加载本地数据集，共 {len(dataset)} 个样本")
        
        for idx, item in enumerate(dataset):
            # 确保有 id 或 idx 字段
            new_item = item.copy()
            if "id" not in new_item and "idx" not in new_item:
                new_item["idx"] = idx
            yield new_item
            
    except Exception as e:
        logger.error(f"加载数据集失败: {e}")
        logger.error("提示: 请确保本地数据集目录存在且包含完整的数据文件")
        raise


def convert_batch(items: List[Dict[str, Any]], image_dir: Optional[Path] = None,
                 save_images: bool = True) -> List[Dict[str, Any]]:
    """
    批量转换 FinMME 数据项
    
    Args:
        items: FinMME 数据项列表
        image_dir: 图片保存目录（如果为 None，则不保存图片）
        save_images: 是否保存图片到本地
        
    Returns:
        转换后的标准格式数据项列表
    """
    converted_items = []
    skipped_count = 0
    
    for item in items:
        try:
            converted = convert_finmme_item(item, image_dir, save_images)
            # 如果返回 None，说明数据缺失必需字段，跳过
            if converted is None:
                skipped_count += 1
                continue
            converted_items.append(converted)
        except Exception as e:
            item_id = item.get("id") or item.get("idx", "unknown")
            logger.error(f"转换数据项失败 (id: {item_id}): {e}")
            skipped_count += 1
            continue
    
    logger.info(f"成功转换 {len(converted_items)}/{len(items)} 条数据（跳过 {skipped_count} 条）")
    return converted_items


def save_converted_data(items: List[Dict[str, Any]], output_path: Path, 
                       format: str = "jsonl"):
    """
    保存转换后的数据到文件
    
    Args:
        items: 转换后的数据项列表
        output_path: 输出文件路径
        format: 输出格式（jsonl 或 json）
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    if format.lower() == "jsonl":
        # 保存为 JSONL 格式（每行一个 JSON 对象）
        with open(output_path, 'w', encoding='utf-8') as f:
            for item in items:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
    else:
        # 保存为 JSON 格式（整个数组）
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
    
    logger.info(f"数据已保存到: {output_path} ({len(items)} 条)")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='FinMME 数据集转换工具 - 将 FinMME 转换为 evaluate_py 标准格式',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 基本用法：使用默认本地目录
  python convert_data.py --output finmme_converted.jsonl

  # 指定本地目录
  python convert_data.py --output finmme_converted.jsonl --local_dir /path/to/local/data

  # 不保存图片（不推荐，evaluate_py 需要图片路径）
  python convert_data.py --output finmme_converted.jsonl --no_save_images

  # 限制转换数量（用于测试）
  python convert_data.py --output finmme_converted.jsonl --limit 100
        """
    )
    
    parser.add_argument('--local_dir', type=str, default=DEFAULT_LOCAL_DATA_DIR,
                       help=f'本地数据集目录路径（默认: {DEFAULT_LOCAL_DATA_DIR}）')
    parser.add_argument('--dataset', default='luojunyu/FinMME', 
                       help='数据集名称（默认: luojunyu/FinMME）')
    parser.add_argument('--split', default='train', 
                       help='数据集分割（默认: train）')
    parser.add_argument('--output', type=str, required=True,
                       help='输出文件路径（支持 .json 或 .jsonl 格式）')
    parser.add_argument('--image_dir', type=str, default=None,
                       help='图片保存目录（默认: 在输出文件所在目录下创建 images 子目录）')
    parser.add_argument('--no_save_images', action='store_true',
                       help='不保存图片（默认会保存图片，如果指定此选项，image_path 将为空，可能导致 evaluate_py 无法加载图片）')
    parser.add_argument('--limit', type=int, default=None,
                       help='限制转换的数据数量（用于测试）')
    parser.add_argument('--format', choices=['json', 'jsonl'], default=None,
                       help='输出格式（默认: 根据输出文件扩展名自动判断）')
    
    args = parser.parse_args()
    
    # 默认保存图片，除非用户指定 --no_save_images
    save_images = not args.no_save_images
    
    # 确定图片保存目录
    output_path = Path(args.output).absolute()
    if save_images:
        if args.image_dir:
            # 使用指定的图片目录
            image_dir = Path(args.image_dir).absolute()
        else:
            # 默认：在输出文件所在目录下创建 images 子目录
            image_dir = output_path.parent / "images"
    else:
        image_dir = None
    
    # 根据输出文件扩展名确定格式
    if args.format:
        output_format = args.format
    elif output_path.suffix.lower() == '.json':
        output_format = 'json'
    else:
        output_format = 'jsonl'
    
    try:
        # 加载数据
        logger.info("开始加载 FinMME 数据集...")
        items = []
        for idx, item in enumerate(load_finmme_from_local(
            local_dir=args.local_dir,
            dataset_name=args.dataset,
            split=args.split
        )):
            items.append(item)
            if args.limit and len(items) >= args.limit:
                break
        
        logger.info(f"成功加载 {len(items)} 条数据")
        
        # 转换数据
        logger.info("开始转换数据...")
        logger.info(f"保存图片: {'是' if save_images else '否'}")
        if save_images and image_dir:
            logger.info(f"图片保存目录: {image_dir}")
        converted_items = convert_batch(items, image_dir, save_images)
        
        if not converted_items:
            logger.error("没有成功转换的数据项")
            return 1
        
        # 保存数据
        logger.info(f"开始保存数据到: {output_path} (格式: {output_format})...")
        save_converted_data(converted_items, output_path, output_format)
        
        logger.info("=" * 60)
        logger.info("转换完成！")
        logger.info(f"输出文件: {output_path}")
        logger.info(f"转换数量: {len(converted_items)} 条")
        if save_images and image_dir:
            logger.info(f"图片保存目录: {image_dir}")
        logger.info("=" * 60)
        
        return 0
        
    except Exception as e:
        logger.error(f"转换失败: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit(main())
