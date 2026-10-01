# Copyright (c) 2026, eCentric and contributors
"""EC Survey - Một khảo sát nội bộ (kiểu Google / Microsoft Forms). Soạn ở /khao-sat/soan, làm ở /khao-sat/lam.

Khong co nghiep vu trong controller: DocType chi cap quyen System Manager, moi truy cap
cua nguoi dung di qua surveys/controllers/api.py -> application/* (kiem quyen o do)."""
from frappe.model.document import Document


class ECSurvey(Document):
    pass
