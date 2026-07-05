# Copyright (c) 2026, eCentric and contributors
"""EC Document Request - Document Request business data only. Approval STATE lives
on EC Approval Request. Level-1 owner approver is resolved from owner_department
(Department.department_head) by the engine's generic 'Reference Department Head'
participant source - not stored/duplicated here. No document master update in v1."""
import frappe
from frappe import _
from frappe.model.document import Document


class ECDocumentRequest(Document):
    def validate(self):
        self._snapshot_lock()

    def _snapshot_lock(self):
        if self.is_new() or not self.approval_request:
            return
        before = self.get_doc_before_save()
        if not before:
            return
        for f in ("department", "owner_department"):
            if before.get(f) and before.get(f) != self.get(f):
                frappe.throw(_("Truong nay la ban chup luc gui va khong the thay doi sau khi gui."))
