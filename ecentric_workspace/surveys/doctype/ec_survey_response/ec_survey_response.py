# Copyright (c) 2026, eCentric and contributors
"""EC Survey Response - Một phiếu trả lời. Ẩn danh thì KHÔNG lưu người trả lời ở đây (xem EC Survey Participant).

Khong co nghiep vu trong controller: DocType chi cap quyen System Manager, moi truy cap
cua nguoi dung di qua surveys/controllers/api.py -> application/* (kiem quyen o do)."""
from frappe.model.document import Document


class ECSurveyResponse(Document):
    pass
