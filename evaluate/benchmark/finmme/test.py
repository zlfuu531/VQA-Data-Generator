import pandas as pd
from datasets import load_dataset

# 1. 以流式模式加载数据集（速度最快，无需完整下载）
dataset_name = "luojunyu/FinMME"
ds = load_dataset(dataset_name, split="train", streaming=True)

# 2. 获取所有列名
# 我们取第一条数据来查看 key
first_item = next(iter(ds))
columns = list(first_item.keys())

print(f"--- 数据集所有列名 ({len(columns)} 个) ---")
for col in columns:
    print(f"- {col}")

print("\n--- 前 3 行数据预览 (不含图像字节数据) ---")
# 3. 转化为 Pandas DataFrame 方便观察（为了整洁，我们排除掉图片列）
preview_data = []
for i, item in enumerate(ds):
    if i >= 3: break
    # 浅拷贝并删除图片数据，防止控制台爆掉
    item_copy = {k: v for k, v in item.items() if k != 'image'}
    preview_data.append(item_copy)

df_preview = pd.DataFrame(preview_data)
print(df_preview)