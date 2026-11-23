# Copyright (c) 2026, eCentric and contributors
"""Host QC Alert Log - Nhật ký gửi cảnh báo Teams. Khoá phiên + lý do + danh sách lỗi: trùng thì không gửi lại.

CRUD thuan (frappe-rules muc 11): khong co nghiep vu; moi truy cap qua host_qc/api/v1.py -> services/."""
from frappe.model.document import Document


class HostQCAlertLog(Document):
    pass
