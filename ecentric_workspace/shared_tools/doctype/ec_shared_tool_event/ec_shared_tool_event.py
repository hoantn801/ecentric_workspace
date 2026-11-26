# Copyright (c) 2026, eCentric and contributors
"""EC Shared Tool Event - nhat ky dung chung, CHI THEM. Sua / xoa bi chan (ke ca qua Desk)."""
import frappe
from frappe.model.document import Document


class ECSharedToolEvent(Document):
    def validate(self):
        if not self.is_new():
            frappe.throw("Nhật ký dùng chung không sửa được.")

    def on_trash(self):
        frappe.throw("Nhật ký dùng chung không xoá được.")
