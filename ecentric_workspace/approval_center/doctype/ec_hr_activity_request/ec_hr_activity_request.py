# Copyright (c) 2026, eCentric and contributors
"""EC HR Activity Request - business data only. Approval STATE on EC Approval Request.
No fulfillment (v1)."""
import frappe
from frappe import _
from frappe.model.document import Document


class ECHRActivityRequest(Document):
    def validate(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            frappe.throw(_("Ngay ket thuc khong the truoc ngay bat dau."))
        if self.estimated_budget is not None and float(self.estimated_budget) < 0:
            frappe.throw(_("Ngan sach du kien khong the am."))
        if self.is_new() or not self.approval_request:
            return
        before = self.get_doc_before_save()
        if before and before.department and before.department != self.department:
            frappe.throw(_("Phong ban la ban chup luc gui va khong the thay doi sau khi gui."))
