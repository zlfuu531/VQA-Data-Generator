#!/usr/bin/env python3
"""
从日志文件中恢复claude模型的数据
"""
import json
import re
from pathlib import Path
from typing import Dict, Any, List, Optional

def parse_log_file(log_file: Path) -> List[Dict[str, Any]]:
    """
    从日志文件中解析claude模型的数据
    """
    results = {}
    current_question_id = None
    in_response_section = False
    response_lines = []
    model_name = "claude-sonnet-4-5-20250929"
    profile = "expert"
    
    with open(log_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # 匹配模型响应开始
        match = re.search(r'📝 模型响应 - claude-sonnet-4-5-20250929.*question_id: (\S+)', line)
        if match:
            current_question_id = match.group(1)
            if current_question_id not in results:
                results[current_question_id] = {
                    "question_id": current_question_id,
                    "profile": profile,
                    "model": {
                        "model_name": model_name,
                        "answer": "",
                        "process": "",
                        "match_gt": False,
                        "response_time": 0.0,
                        "judge_reasoning": ""
                    }
                }
            in_response_section = False
            response_lines = []
            i += 1
            continue
        
        # 匹配完整响应对象开始
        if line.strip() == "完整响应对象:":
            in_response_section = True
            response_lines = []
            i += 1
            continue
        
        # 收集响应对象内容
        if in_response_section and current_question_id:
            # 检查是否到达响应对象结束
            if line.strip().startswith("=" * 80):
                # 解析响应对象
                try:
                    response_text = ''.join(response_lines)
                    response_obj = json.loads(response_text)
                    
                    # 提取answer
                    if response_obj.get("choices") and len(response_obj["choices"]) > 0:
                        message = response_obj["choices"][0].get("message", {})
                        content = message.get("content", "")
                        results[current_question_id]["model"]["answer"] = content
                        results[current_question_id]["model"]["process"] = content
                        
                        # 提取usage信息
                        if "usage" in response_obj:
                            usage = response_obj["usage"]
                            # 可以记录token使用情况，但response_time无法从日志中获取
                except json.JSONDecodeError as e:
                    print(f"  解析响应对象失败 {current_question_id}: {e}")
                except Exception as e:
                    print(f"  处理响应对象失败 {current_question_id}: {e}")
                
                in_response_section = False
                response_lines = []
                i += 1
                continue
            else:
                response_lines.append(line)
                i += 1
                continue
        
        # 匹配裁判模型部分
        judge_match = re.search(r'⚖️ 裁判模型 - claude-sonnet-4-5-20250929.*question_id: (\S+)', line)
        if judge_match:
            qid = judge_match.group(1)
            if qid not in results:
                results[qid] = {
                    "question_id": qid,
                    "profile": profile,
                    "model": {
                        "model_name": model_name,
                        "answer": "",
                        "process": "",
                        "match_gt": False,
                        "response_time": 0.0,
                        "judge_reasoning": ""
                    }
                }
            # 读取接下来的几行，查找评判结果和理由
            for j in range(i+1, min(i+30, len(lines))):
                judge_line = lines[j]
                # 检查是否到达下一个记录的开始（分隔符）
                if judge_line.strip().startswith("=" * 80) or (judge_line.strip().startswith("-" * 80) and len(judge_line.strip()) > 50 and j > i+5):
                    break
                
                if "评判结果:" in judge_line:
                    result_text = judge_line.split("评判结果:", 1)[1].strip()
                    # 处理多种格式：✅ 一致、❌ 不一致、✓、✗等
                    is_correct = ("✅" in result_text or "一致" in result_text or "✓" in result_text) and "❌" not in result_text and "不一致" not in result_text and "✗" not in result_text
                    results[qid]["model"]["match_gt"] = is_correct
                
                if "评判理由:" in judge_line:
                    # 提取完整的评判理由
                    reasoning = judge_line.split("评判理由:", 1)[1].strip()
                    # 如果理由在同一行，直接使用；否则继续读取下一行
                    if not reasoning:
                        # 尝试读取下一行
                        if j+1 < len(lines):
                            next_line = lines[j+1].strip()
                            if next_line and not next_line.startswith("耗时:") and not next_line.startswith("-"):
                                reasoning = next_line
                    if reasoning:
                        results[qid]["model"]["judge_reasoning"] = reasoning
            i += 1
            continue
        
        i += 1
    
    return list(results.values())

def main():
    log_dir = Path("/home/zenglingfeng/qa_pipline12-7/evaluate/evaluate_logs1222")
    output_file = Path("/home/zenglingfeng/qa_pipline12-7/evaluate/outputs/expert/claude-sonnet-4-5-20250929/last_evaluate.jsonl")
    
    # 找到最新的包含claude数据的日志文件
    log_files = sorted(log_dir.glob("eval_*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    
    all_results = []
    seen_ids = set()
    
    for log_file in log_files:
        print(f"处理日志文件: {log_file.name}")
        try:
            records = parse_log_file(log_file)
            for record in records:
                qid = record.get("question_id")
                if qid and qid not in seen_ids:
                    seen_ids.add(qid)
                    all_results.append(record)
            print(f"  从 {log_file.name} 提取了 {len(records)} 条记录")
        except Exception as e:
            print(f"  处理 {log_file.name} 失败: {e}")
            continue
    
    print(f"\n总共提取了 {len(all_results)} 条唯一记录")
    
    # 写入文件
    if all_results:
        # 写入统计信息占位符
        stats_placeholder = {
            "statistics": {
                "total": {"total_count": 0, "correct_count": 0, "accuracy": 0.0},
                "by_model": {},
                "by_profile": {},
                "by_category": {}
            }
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(json.dumps(stats_placeholder, ensure_ascii=False) + '\n')
            for record in all_results:
                f.write(json.dumps(record, ensure_ascii=False) + '\n')
        
        print(f"已写入 {len(all_results)} 条记录到 {output_file}")
    else:
        print("没有提取到任何记录！")

if __name__ == "__main__":
    main()

