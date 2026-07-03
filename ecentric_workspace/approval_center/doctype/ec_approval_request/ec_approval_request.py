# Copyright (c) 2026, eCentric and contributors
"""EC Approval Request - single source of truth for approval STATE of one
submitted business document. Generic statuses; stage names live on the levels.

reference_key is a DB-UNIQUE partial key (= '<reference_doctype>::<reference_name>'
only while OPEN, NULL when terminal) so concurrent writes cannot create two open
requests for one business document; a fresh request is allowed once the prior
one is terminal."""
import frappe
from frappe import _
from frappe.model.document import Document

_OPEN = ("Pending", "Information Required")


class ECApprovalRequest(Document):
    def validate(self):
        if self.approval_status in _OPEN:
            self.reference_key = "{0}::{1}".format(self.reference_doctype, self.reference_name)
            dup = frappe.get_all("EC Approval Request", filters={
                "reference_key": self.reference_key,
                "approval_status": ["in", _OPEN],
                "name": ["!=", self.name or ""]})
            if dup:
                frappe.throw(_("An open approval request already exists for {0} {1}.").format(
                    self.reference_doctype, self.reference_name))
        else:
            self.reference_key = None  # freed once terminal (NULLs repeat under unique index)
