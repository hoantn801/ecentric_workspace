# Copyright (c) 2026, eCentric and contributors
"""Append-only esign audit event (mirrors the EC Approval Action immutability pattern).
Insert-only for EVERY role including System Manager; updates and deletes throw."""
import frappe
from frappe import _
from frappe.model.document import Document


class ECDigitalSignatureEvent(Document):
    def validate(self):
        if not self.is_new():
            frappe.throw(_("EC Digital Signature Event is append-only; existing events cannot be edited."))

    def on_trash(self):
        frappe.throw(_("EC Digital Signature Event is append-only; events cannot be deleted."))
