# Copyright (c) 2026, eCentric and contributors
"""EC Data Request - Data Request business data only. Approval STATE lives on
EC Approval Request (no approval_status duplicated here). Orchestration is in
ecentric_workspace.approval_center.data_request.service. No external integration."""
import frappe
from frappe import _
from frappe.model.document import Document


class ECDataRequest(Document):
    def validate(self):
        self._department_snapshot_lock()

    def _department_snapshot_lock(self):
        if self.is_new() or not self.approval_request:
            return
        before = self.get_doc_before_save()
        if before and before.department and before.department != self.department:
            frappe.throw(_("Phong ban la ban chup luc gui va khong the thay doi sau khi gui."))
