# Copyright (c) 2026, eCentric and contributors
import frappe
from frappe import _
from frappe.model.document import Document


class ECDigitalSignatureRequest(Document):
    def validate(self):
        # actor_type-conditional requirements. request_level/approver_row are NOT globally
        # optional: they remain mandatory for an Approval-Level signer and are unused for a
        # Requester signer (pre-approval). Requester rows must carry actor_user.
        actor_type = self.actor_type or "Approval Level"
        if actor_type == "Approval Level":
            if not self.request_level or not self.approver_row:
                frappe.throw(_("Approval-Level signature request requires request_level and approver_row."))
        elif actor_type == "Requester":
            if not self.actor_user:
                frappe.throw(_("Requester signature request requires actor_user."))
            # a requester row never carries approver-level context
            self.request_level = None
            self.approver_row = None
