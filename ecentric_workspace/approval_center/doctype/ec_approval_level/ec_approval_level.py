# Copyright (c) 2026, eCentric and contributors
"""EC Approval Level - one dynamic level under a process."""
import frappe
from frappe import _
from frappe.model.document import Document

from ecentric_workspace.approval_center.engine.participant_rules import validate_participants


class ECApprovalLevel(Document):
    def validate(self):
        if self.level_no is None:
            frappe.throw(_("level_no is required."))
        dup = frappe.get_all("EC Approval Level", filters={
            "process": self.process, "level_no": self.level_no, "name": ["!=", self.name or ""]})
        if dup:
            frappe.throw(_("Duplicate level_no {0} for this process.").format(self.level_no))
        if self.approval_mode == "Minimum Count":
            appr = [p for p in (self.participants or []) if p.participant_purpose == "Approver"]
            if not self.minimum_approvals or self.minimum_approvals < 1:
                frappe.throw(_("minimum_approvals must be >= 1 when approval_mode is Minimum Count."))
            if self.minimum_approvals > len(appr) and appr:
                frappe.throw(_("minimum_approvals cannot exceed the number of approver participants."))
        else:
            self.minimum_approvals = 0
        validate_participants(self, "participants")
