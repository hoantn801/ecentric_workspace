# Copyright (c) 2026, eCentric and contributors
"""EC Asset Request - business data only. Approval STATE on EC Approval Request.
quantity must be > 0. operation_expected_completion_date recorded by Operation
(never auto-defaulted). No external procurement integration (v1)."""
import frappe
from frappe import _
from frappe.model.document import Document


class ECAssetRequest(Document):
    def validate(self):
        if self.quantity is not None and int(self.quantity) <= 0:
            frappe.throw(_("So luong phai lon hon 0."))
        if self.is_new() or not self.approval_request:
            return
        before = self.get_doc_before_save()
        if before and before.department and before.department != self.department:
            frappe.throw(_("Phong ban la ban chup luc gui va khong the thay doi sau khi gui."))
