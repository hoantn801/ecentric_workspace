# Copyright (c) 2026, eCentric and contributors
"""EC Resignation Request - business data only. Approval STATE lives on EC Approval Request.
Direct Manager review + HR fulfillment. No external integration."""
import frappe
from frappe import _
from frappe.model.document import Document


class ECResignationRequest(Document):
    def validate(self):
        if self.is_new() or not self.approval_request:
            return
        before = self.get_doc_before_save()
        if before and before.department and before.department != self.department:
            frappe.throw(_("Phong ban la ban chup luc gui va khong the thay doi sau khi gui."))
