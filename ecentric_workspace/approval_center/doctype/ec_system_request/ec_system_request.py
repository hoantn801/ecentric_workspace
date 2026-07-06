# Copyright (c) 2026, eCentric and contributors
"""EC System Request - business data only. Approval STATE on EC Approval Request.
operation_expected_completion_date is recorded by Operation (never auto-defaulted).
No external integration."""
import frappe
from frappe import _
from frappe.model.document import Document


class ECSystemRequest(Document):
    def validate(self):
        if self.is_new() or not self.approval_request:
            return
        before = self.get_doc_before_save()
        if before and before.department and before.department != self.department:
            frappe.throw(_("Phong ban la ban chup luc gui va khong the thay doi sau khi gui."))
