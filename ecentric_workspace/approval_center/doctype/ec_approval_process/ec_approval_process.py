# Copyright (c) 2026, eCentric and contributors
"""EC Approval Process - one versioned process configuration record.

active_process_key is a DB-UNIQUE partial key (= approval_type only while Active,
NULL otherwise) so concurrent writes cannot create two Active processes for one
approval_type. The controller pre-check gives a friendly error before the DB
constraint fires."""
import frappe
from frappe import _
from frappe.model.document import Document

from ecentric_workspace.approval_center.engine.participant_rules import validate_participants


class ECApprovalProcess(Document):
    def validate(self):
        if not self.is_new():
            before = self.get_doc_before_save()
            if before and before.process_code and before.process_code != self.process_code:
                frappe.throw(_("process_code is immutable."))
        # DB-unique partial key: set only while Active, else NULL (NULLs repeat).
        self.active_process_key = self.approval_type if self.status == "Active" else None
        if self.status == "Active":
            dup = frappe.get_all("EC Approval Process", filters={
                "approval_type": self.approval_type, "status": "Active",
                "name": ["!=", self.name or ""]})
            if dup:
                frappe.throw(_("Another Active process already exists for approval_type {0}. "
                               "Retire it first.").format(self.approval_type))
        validate_participants(self, "participants")
