# Copyright (c) 2026, eCentric and contributors
"""EC Approval Request Level - immutable runtime snapshot of a configured level.
Config fields are frozen after insert; only runtime status/timestamps mutate."""
import frappe
from frappe import _
from frappe.model.document import Document

_FROZEN = ("approval_request", "level_no", "level_name", "approval_mode",
           "minimum_approvals", "mandatory", "source_process_level")


class ECApprovalRequestLevel(Document):
    def validate(self):
        if self.is_new():
            return
        before = self.get_doc_before_save()
        if not before:
            return
        for f in _FROZEN:
            if (getattr(self, f, None) or None) != (getattr(before, f, None) or None):
                frappe.throw(_("Snapshot field '{0}' is frozen and cannot change after submission.").format(f))
