import re
import os

# ==========================================
# 1. 📂 设定：日志文件的绝对路径
# ==========================================

LOG_FILE_PATH = r"./module2_logs/20251204_112228_qa_test_mix_prompt2-20.log"#mudule2_logs or module1_logs
# ==========================================
# 2. ⚙️ 设定：你想计算多少道题目的预算？
# ==========================================
TARGET_COUNT = 10000  # 例如：计算 1000 次请求的总费用

# ==========================================
# 3. 💰 设定：模型价格字典 (单位：元/百万 Tokens)
#    格式：{"模型名": {"in": 输入价格, "out": 输出价格, "currency": "货币符号"}}
# ==========================================
MODEL_PRICING = {
    # 阿里云 Qwen 系列 (刊例价)(单位：元/百万 Tokens)
    "Qwen3-VL-Plus":      {"in": 1.0,   "out": 10.0,  "currency": "¥"},
    "Qwen-VL-Max":       {"in": 1.6,  "out": 4.0,  "currency": "¥"},
    "doubao-seed-1-6-251015": {"in": 0.8, "out": 2.0, "currency": "¥"},
    "doubao-seed-1-6-vision-250815": {"in": 0.8, "out": 8.0, "currency": "¥"}  
}

def calculate_budget():
    # --- 1. 读取文件 ---
    if not os.path.exists(LOG_FILE_PATH):
        print(f"❌ 错误：找不到文件 -> {LOG_FILE_PATH}")
        return

    try:
        with open(LOG_FILE_PATH, 'r', encoding='utf-8') as f:
            log_content = f.read()
    except Exception as e:
        print(f"❌ 读取文件出错: {e}")
        return

    # --- 2. 解析日志 ---
    # 使用正则提取所有的 prompt_tokens 和 completion_tokens
    prompts = [int(x) for x in re.findall(r'"prompt_tokens":\s*(\d+)', log_content)]
    completions = [int(x) for x in re.findall(r'"completion_tokens":\s*(\d+)', log_content)]

    count = len(prompts)
    if count == 0:
        print("⚠️ 警告：文件中未匹配到 token 数据。请检查日志格式是否包含 'prompt_tokens' 和 'completion_tokens'。")
        return

    avg_prompt = sum(prompts) / count
    avg_completion = sum(completions) / count
    avg_total = avg_prompt + avg_completion

    print(f"\n{'='*60}")
    print(f"📊 日志分析报告")
    print(f"{'='*60}")
    print(f"📂 文件路径: {os.path.basename(LOG_FILE_PATH)}")
    print(f"🔢 样本数量: {count} 条")
    print(f"{'-'*60}")
    print(f"🔹 平均输入 (Prompt):      {avg_prompt:.0f} tokens")
    print(f"🔸 平均输出 (Completion):  {avg_completion:.0f} tokens")
    print(f"📈 平均单次总消耗:        {avg_total:.0f} tokens")
    print(f"{'-'*60}")
    print(f"🎯 预算目标: 运行 {TARGET_COUNT} 次请求")
    print(f"{'='*60}\n")

    # --- 3. 计算各模型价格 ---
    print(f"{'模型名称':<20} | {'单次成本':<12} | {'总预算 (' + str(TARGET_COUNT) + '次)':<15} | {'价格构成 (In/Out)'}")
    print(f"{'-'*20}-+-{'-'*12}-+-{'-'*15}-+-{'-'*20}")

    for model, price in MODEL_PRICING.items():
        # 单次成本计算
        cost_in_per_req = (avg_prompt / 1_000_000) * price["in"]
        cost_out_per_req = (avg_completion / 1_000_000) * price["out"]
        single_cost = cost_in_per_req + cost_out_per_req
        
        # 总成本
        total_cost = single_cost * TARGET_COUNT
        currency = price["currency"]
        
        print(f"{model:<20} | {currency} {single_cost:<10.4f} | {currency} {total_cost:<13,.2f} | In:{price['in']} / Out:{price['out']}")

    print(f"{'='*60}")
    print(f"📌 注：价格单位为 元/百万Tokens (per Million Tokens)")

if __name__ == "__main__":
    calculate_budget()