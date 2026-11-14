# Copyright (c) 2026, eCentric and contributors
"""EC Training Topic - Chủ đề đề xuất cho bài học tới - mọi người bình chọn (mỗi người 3 phiếu, trả lại khi chủ đề thành bài)

Khong co nghiep vu trong controller: DocType chi cap quyen System Manager, moi truy cap cua
nguoi dung di qua dao_tao/controllers/api.py -> application/* (kiem quyen o access.py)."""
from frappe.model.document import Document


class ECTrainingTopic(Document):
    pass
