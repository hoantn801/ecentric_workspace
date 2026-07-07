# Copyright (c) 2026, eCentric and contributors
"""EC Hiring Request - business data only. Approval STATE lives on EC Approval Request.
Direct Manager -> HR -> CEO (no fulfillment). line_manager is business info about the future
hire's manager, NOT an approval resolver."""
import frappe
from frappe import _
from frappe.model.document import Document


class ECHiringRequest(Document):
    def validate(self):
        if self.is_new() or not self.approval_request:
            return
        before = self.get_doc_before_save()
        if before and before.department and before.department != self.department:
            frappe.throw(_("Phong ban la ban chup luc gui va khong the thay doi sau khi gui."))
