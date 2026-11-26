# Copyright (c) 2026, eCentric and contributors
"""EC Shared Tool - cau hinh mot cong cu dung chung. CRUD thuan: chi kiem so phut hop le
(khong goi he thong ngoai, khong nhanh theo trang thai -> khong tach service, frappe-rules muc 11)."""
import frappe
from frappe.model.document import Document

_MINUTE_FIELDS = ("lease_minutes", "ready_minutes", "extend_minutes", "idle_minutes")


class ECSharedTool(Document):
    def validate(self):
        for f in _MINUTE_FIELDS:
            if int(self.get(f) or 0) < 1:
                frappe.throw("%s phải từ 1 phút trở lên." % self.meta.get_label(f))
