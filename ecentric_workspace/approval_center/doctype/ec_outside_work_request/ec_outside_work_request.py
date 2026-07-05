# Copyright (c) 2026, eCentric and contributors
"""EC Outside Work Request - Outside Work business data only.
Approval STATE lives on EC Approval Request (no approval_status here). This
controller enforces business-intrinsic validation; orchestration is in
ecentric_workspace.approval_center.outside_work.service. No attendance/master
update is performed in v1."""
import frappe
from frappe import _
from frappe.model.document import Document


class ECOutsideWorkRequest(Document):
    def validate(self):
        self._validate_dates()
        self._validate_duration()
        self._department_snapshot_lock()

    def _validate_dates(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            frappe.throw(_("Ngày kết thúc không thể trước ngày bắt đầu."))

    def _validate_duration(self):
        if self.duration_days is not None and float(self.duration_days) <= 0:
            frappe.throw(_("Thời lượng (ngày) phải lớn hơn 0."))

    def _department_snapshot_lock(self):
        if self.is_new() or not self.approval_request:
            return
        before = self.get_doc_before_save()
        if before and before.department and before.department != self.department:
            frappe.throw(_("Phòng ban là bản chụp lúc gửi và không thể thay đổi sau khi gửi."))
