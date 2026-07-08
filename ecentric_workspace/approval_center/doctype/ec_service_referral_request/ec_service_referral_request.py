# Copyright (c) 2026, eCentric and contributors
"""EC Service Referral Request - business data only. Approval STATE lives on EC Approval Request.
Orchestration in the matching service module. Approval-only v1: no external
integration and NO master-data mutation."""
import frappe
from frappe import _
from frappe.model.document import Document


class ECServiceReferralRequest(Document):
    def validate(self):
        self._department_snapshot_lock()

    def _department_snapshot_lock(self):
        if self.is_new() or not self.approval_request:
            return
        before = self.get_doc_before_save()
        if before and before.department and before.department != self.department:
            frappe.throw(_("Phong ban la ban chup luc gui va khong the thay doi sau khi gui."))
