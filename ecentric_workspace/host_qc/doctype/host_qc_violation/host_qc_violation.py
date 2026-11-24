# Copyright (c) 2026, eCentric and contributors
"""Host QC Violation - Một lỗi app phát hiện. Duyệt bằng 3 nút trên form; điểm phiên tự tính lại.

CRUD thuan (frappe-rules muc 11): khong co nghiep vu; moi truy cap qua host_qc/api/v1.py -> services/."""
from frappe.model.document import Document


class HostQCViolation(Document):
    pass
