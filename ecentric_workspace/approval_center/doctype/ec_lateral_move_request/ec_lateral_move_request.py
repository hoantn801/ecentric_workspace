# Copyright (c) 2026, eCentric and contributors
"""EC Lateral Move Request - business data only. Approval STATE lives on EC Approval Request.
Current Manager -> New Line Manager (from new_line_manager field) -> HR -> CEO (no fulfillment)."""
import frappe
from frappe import _
from frappe.model.document import Document


class ECLateralMoveRequest(Document):
    def validate(self):
        if self.is_new() or not self.approval_request:
            return
        before = self.get_doc_before_save()
        if before and before.new_line_manager and before.new_line_manager != self.new_line_manager:
            frappe.throw(_("Quan ly moi la ban chup luc gui va khong the thay doi sau khi gui."))
