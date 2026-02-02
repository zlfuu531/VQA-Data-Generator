#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FinMME 数据集转换脚本（命令行入口）
将 FinMME 数据集转换为 evaluate_py 评测框架需要的标准格式

使用方法:
    python convert_finmme.py --output output.jsonl
    python convert_finmme.py --output output.jsonl --local_dir /path/to/local/data
"""

import sys
from pathlib import Path

# 添加当前目录到路径，以便导入模块
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

# 导入转换函数（从 convert_data 模块导入）
from convert_data import main

# 直接调用 convert_data 的 main 函数
if __name__ == "__main__":
    exit(main())

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='FinMME 数据集转换工具 - 将 FinMME 转换为 evaluate_py 标准格式',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 基本用法：从 HuggingFace 加载并转换
  python convert_finmme.py --output finmme_converted.jsonl

  # 从本地缓存加载
  python convert_finmme.py --output finmme_converted.jsonl --cache_dir ~/.cache/huggingface/datasets

  # 不保存图片（默认会保存）
  python convert_finmme.py --output finmme_converted.jsonl --no_save_images

  # 限制转换数量（用于测试）
  python convert_finmme.py --output finmme_converted.jsonl --limit 100
        """
    )
    
    parser.add_argument('--dataset', default='luojunyu/FinMME', 
                       help='数据集名称（HuggingFace，默认: luojunyu/FinMME）')
    parser.add_argument('--split', default='train', 
                       help='数据集分割（默认: train）')
    parser.add_argument('--cache_dir', type=str, default=None,
                       help='本地缓存目录（如果提供则从本地加载）')
    parser.add_argument('--output', type=str, required=True,
                       help='输出文件路径（支持 .json 或 .jsonl 格式）')
    parser.add_argument('--no_save_images', action='store_true',
                       help='不保存图片（默认会保存图片，如果指定此选项，image_path 将为空，可能导致 evaluate_py 无法加载图片）')
    parser.add_argument('--limit', type=int, default=None,
                       help='限制转换的数据数量（用于测试）')
    parser.add_argument('--format', choices=['json', 'jsonl'], default=None,
                       help='输出格式（默认: 根据输出文件扩展名自动判断）')
    
    args = parser.parse_args()
    
    # 默认保存图片，除非用户指定 --no_save_images
    save_images = not args.no_save_images
    
    # 确定输出目录（用于保存图片）
    output_path = Path(args.output).absolute()
    output_dir = output_path.parent if save_images else None
    
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
        logger.info(f"数据集: {args.dataset}, 分割: {args.split}")
        if args.cache_dir:
            logger.info(f"使用本地缓存目录: {args.cache_dir}")
        
        items = []
        for idx, item in enumerate(load_finmme_from_huggingface(
            dataset_name=args.dataset,
            split=args.split,
            cache_dir=args.cache_dir,
            streaming=False  # 为了支持 limit 参数，不使用 streaming
        )):
            items.append(item)
            if args.limit and len(items) >= args.limit:
                break
        
        logger.info(f"成功加载 {len(items)} 条数据")
        
        # 转换数据
        logger.info("开始转换数据...")
        logger.info(f"保存图片: {'是' if save_images else '否'}")
        converted_items = convert_batch(items, output_dir, save_images)
        
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
        if save_images:
            logger.info(f"图片保存目录: {output_dir / 'images'}")
        logger.info("=" * 60)
        
        return 0
        
    except Exception as e:
        logger.error(f"转换失败: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit(main())

