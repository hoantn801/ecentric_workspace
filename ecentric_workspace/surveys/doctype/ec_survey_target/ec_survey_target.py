# Copyright (c) 2026, eCentric and contributors
"""EC Survey Target - Một dòng đối tượng của khảo sát: phòng ban tham gia (tính cả phòng con), người được chọn, hoặc người bị loại trừ.

Khong co nghiep vu trong controller: DocType chi cap quyen System Manager, moi truy cap
cua nguoi dung di qua surveys/controllers/api.py -> application/* (kiem quyen o do)."""
from frappe.model.document import Document


class ECSurveyTarget(Document):
    pass
