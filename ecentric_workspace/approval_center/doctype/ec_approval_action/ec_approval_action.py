# Copyright (c) 2026, eCentric and contributors
"""EC Approval Action - append-only audit log for the Approval Center engine.
Separate domain from the legacy /approval 'EC Approval Log'. No edits/deletes."""
import frappe
from frappe import _
from frappe.model.document import Document


class ECApprovalAction(Document):
    def validate(self):
        if not self.is_new():
            frappe.throw(_("EC Approval Action is append-only; existing actions cannot be edited."))

    def on_trash(self):
        frappe.throw(_("EC Approval Action is append-only; actions cannot be deleted."))
