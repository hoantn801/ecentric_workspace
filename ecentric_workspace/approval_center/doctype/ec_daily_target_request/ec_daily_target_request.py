# Copyright (c) 2026, eCentric and contributors
"""EC Daily Target Request - business data only. Two scopes (Project level /
Consolidated-Total) map to two Approval Processes selected at submit; approvers
come from the process config. No fulfillment (v1)."""
import frappe
from frappe import _
from frappe.model.document import Document


class ECDailyTargetRequest(Document):
    def validate(self):
        self._validate_target_month()
        self._snapshot_lock()

    def _validate_target_month(self):
        if self.target_month:
            try:
                d = frappe.utils.getdate(self.target_month)
            except Exception:
                return
            if d.day != 1:
                frappe.throw(_("Vui lòng chọn ngày đầu tiên của tháng mục tiêu (ngày 01)."))

    def _snapshot_lock(self):
        if self.is_new() or not self.approval_request:
            return
        before = self.get_doc_before_save()
        if before and before.department and before.department != self.department:
            frappe.throw(_("Phòng ban là bản chụp lúc gửi và không thể thay đổi sau khi gửi."))
