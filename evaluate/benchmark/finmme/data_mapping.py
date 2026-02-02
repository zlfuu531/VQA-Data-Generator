"""
FinMME 数据集字段映射配置
将 FinMME 数据集的字段映射到 evaluate_py 评测框架需要的标准字段

核心字段映射：
- id/idx -> question_id
- image -> image_path (需要保存到本地)
- question_text -> question
- question_type -> question_type (直接使用)
- options -> options (直接使用)
- answer -> answer (直接使用)

其他字段会原样保留，但不参与评测和评分
"""

# evaluate_py 需要的必需字段
REQUIRED_FIELDS = ["question_id", "question", "answer"]

# 核心字段（参与评测的字段）
CORE_FIELDS = ["question_id", "image_id", "question", "question_type", "options", "answer", "image_path"]

