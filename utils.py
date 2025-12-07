"""
工具函数模块
"""
import json
import os
import threading
from typing import Dict, List, Any

# 全局锁
file_lock = threading.Lock()

def ensure_dir(directory: str):
    """确保目录存在"""
    os.makedirs(directory, exist_ok=True)

def save_json(data: Any, filepath: str, indent: int = 4):
    """
    线程安全地保存JSON文件
    
    Args:
        data: 要保存的数据
        filepath: 文件路径（如果为None，会抛出错误）
        indent: JSON缩进（默认4）
    """
    if filepath is None:
        raise ValueError("文件路径不能为None")
    
    # 确保目录存在
    dir_path = os.path.dirname(filepath)
    if dir_path:  # 如果路径包含目录
        ensure_dir(dir_path)
    else:
        # 如果只是文件名，使用当前目录
        filepath = os.path.join(".", filepath)
    
    with file_lock:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=indent)

def load_json(filepath: str) -> Any:
    """
    加载JSON或JSONL文件
    
    自动检测文件格式：
    1. 先尝试按标准JSON格式解析（支持.json和.jsonl扩展名）
    2. 如果失败，再尝试按JSONL格式解析（每行一个JSON对象）
    
    Args:
        filepath: 文件路径（支持.json和.jsonl格式）
    
    Returns:
        如果是JSON格式，返回解析后的对象
        如果是JSONL格式，返回包含所有行的列表
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"文件不存在: {filepath}")
    
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read().strip()
    
    # 首先尝试按标准JSON格式解析（适用于JSON数组或JSON对象）
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # 如果标准JSON解析失败，尝试按JSONL格式解析（每行一个JSON对象）
        items = []
        with open(filepath, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:  # 跳过空行
                    continue
                try:
                    item = json.loads(line)
                    items.append(item)
                except json.JSONDecodeError as e:
                    print(f"警告：第 {line_num} 行JSON解析失败: {e}")
                    continue
        if items:
            return items
        else:
            raise ValueError(f"无法解析文件 {filepath}：既不是标准JSON格式，也不是有效的JSONL格式")

def extract_answer_from_boxed(text: str) -> str:
    """
    从\\boxed{}格式中提取答案
    支持嵌套大括号的情况（例如：\\boxed{答案中包含\\boldsymbol{x}这样的LaTeX命令}）
    
    优先使用手动匹配大括号的方法，因为正则表达式无法正确处理嵌套的大括号。
    如果文本中有多个\\boxed{}，会找到所有匹配并返回最后一个（通常是最终答案）。
    """
    # 手动查找所有 \\boxed{ ... } 配对，支持嵌套大括号
    all_matches = []
    pos = 0
    
    while True:
        # 查找下一个 \\boxed{
        start_idx = text.find('\\boxed{', pos)
        if start_idx == -1:
            break
        
        # 从 \\boxed{ 后面开始匹配大括号
        brace_start = start_idx + len('\\boxed{')
        depth = 0
        end_idx = -1
        
        for i in range(brace_start, len(text)):
            if text[i] == '{':
                depth += 1
            elif text[i] == '}':
                if depth == 0:
                    # 找到匹配的右大括号
                    end_idx = i
                    break
                depth -= 1
        
        if end_idx != -1:
            # 成功找到一对匹配的大括号
            content = text[brace_start:end_idx].strip()
            all_matches.append(content)
            pos = end_idx + 1
        else:
            # 没有找到匹配的右大括号，跳过这个位置
            pos = brace_start
    
    # 返回最后一个匹配（通常是最终答案）
    if all_matches:
        return all_matches[-1]
    
    return ""

def _flatten_answer(answer: Any) -> str:
    """
    将各种类型的答案统一摊平成字符串：
    - 字符串: 原样去除多余空白
    - 字典: 按 key 排序，格式为 "k1: v1; k2: v2"
      典型应用：多轮对话答案 {"round1": "...", "round2": "..."}
    - 列表/元组: 用分号拼接
    - 其他类型: 使用 str() 转字符串
    """
    import re

    # 字典（多轮 / 多字段答案）
    if isinstance(answer, dict):
        # 按 key 排序保证稳定性
        parts = []
        for k in sorted(answer.keys()):
            v = answer[k]
            # 递归扁平化 value，避免嵌套 dict/list
            v_str = _flatten_answer(v)
            parts.append(f"{k}: {v_str}")
        joined = "; ".join(parts)
        return re.sub(r'\s+', ' ', joined).strip()

    # 列表或元组：常用于多选题答案拆分
    if isinstance(answer, (list, tuple)):
        parts = [_flatten_answer(x) for x in answer]
        joined = "; ".join(parts)
        return re.sub(r'\s+', ' ', joined).strip()

    # 其他类型统一转字符串
    text = str(answer)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def normalize_answer(answer: Any) -> str:
    """标准化答案，用于比较（支持字符串、多轮字典、列表等）"""
    return _flatten_answer(answer)

def compare_answers(answer1: str, answer2: str) -> bool:
    """比较两个答案是否相同"""
    return normalize_answer(answer1) == normalize_answer(answer2)

def count_agreement(answers: List[str], gt: str) -> int:
    """统计有多少个答案与GT相同"""
    count = 0
    for answer in answers:
        if compare_answers(answer, gt):
            count += 1
    return count

def get_agreement_level(answers: List[str], gt: str) -> str:
    """根据答案一致性获取分类级别"""
    agreement_count = count_agreement(answers, gt)
    if agreement_count == 3:
        return "L1"
    elif agreement_count == 2:
        return "L2"
    elif agreement_count == 1:
        return "L3"
    else:
        return "L4"

def merge_batch_files(batch_dir: str, output_file: str, prefix: str = "batch_"):
    """合并批次文件"""
    all_results = []
    batch_files = []
    
    if not os.path.exists(batch_dir):
        return
    
    for filename in os.listdir(batch_dir):
        if filename.startswith(prefix) and filename.endswith(".json"):
            batch_files.append(filename)
    
    batch_files.sort()
    for filename in batch_files:
        filepath = os.path.join(batch_dir, filename)
        try:
            batch_data = load_json(filepath)
            if isinstance(batch_data, list):
                all_results.extend(batch_data)
            else:
                all_results.append(batch_data)
        except Exception as e:
            print(f"警告：无法读取批次文件 {filename}: {e}")
    
    if all_results:
        save_json(all_results, output_file)
        print(f"✅ 已合并 {len(all_results)} 条结果到: {output_file}")
        
        # 删除批次文件
        for filename in batch_files:
            try:
                os.remove(os.path.join(batch_dir, filename))
            except Exception as e:
                print(f"警告：无法删除批次文件 {filename}: {e}")

def format_qa_item(image_path: str, question: str, answer: str, 
                   image_id: str = None, metadata: Dict = None) -> Dict:
    """格式化QA数据项"""
    item = {
        "image_path": image_path,
        "image_id": image_id or os.path.basename(image_path),
        "Q": question,
        "Answer": answer,
        "GT": answer,  # 初始GT就是生成的答案
        "metadata": metadata or {}
    }
    return item

