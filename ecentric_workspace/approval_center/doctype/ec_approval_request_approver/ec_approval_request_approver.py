# Copyright (c) 2026, eCentric and contributors
"""EC Approval Request Approver - runtime per-approver state (NOT the audit log).
Directly queryable for 'Can toi duyet'. Unique approver per request level."""
import frappe
from frappe import _
from frappe.model.document import Document


class ECApprovalRequestApprover(Document):
    def validate(self):
        dup = frappe.get_all("EC Approval Request Approver", filters={
            "request_level": self.request_level, "approver": self.approver,
            "name": ["!=", self.name or ""]})
        if dup:
            frappe.throw(_("Duplicate approver {0} for this request level.").format(self.approver))
