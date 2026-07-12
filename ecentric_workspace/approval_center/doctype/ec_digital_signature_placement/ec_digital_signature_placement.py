# Copyright (c) 2026, eCentric and contributors
"""Signature placement rectangle. page_index is 1-based (SCTS convention)."""
import frappe
from frappe import _
from frappe.model.document import Document


class ECDigitalSignaturePlacement(Document):
    def validate(self):
        if (self.page_index or 0) < 1:
            frappe.throw(_("page_index is 1-based and must be >= 1."))
        if (self.width or 0) <= 0 or (self.height or 0) <= 0:
            frappe.throw(_("Placement width/height must be positive."))
