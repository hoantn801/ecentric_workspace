# Copyright (c) 2026, eCentric and contributors
"""EC Promotion Request - business data only. Approval STATE lives on EC Approval Request.
Direct Manager -> CnB -> HOF -> CEO (no fulfillment). Salary visible to all approvers (v1)."""
import frappe
from frappe import _
from frappe.model.document import Document


class ECPromotionRequest(Document):
    def validate(self):
        if self.is_new() or not self.approval_request:
            return
        before = self.get_doc_before_save()
        if before and before.department and before.department != self.department:
            frappe.throw(_("Phong ban la ban chup luc gui va khong the thay doi sau khi gui."))
