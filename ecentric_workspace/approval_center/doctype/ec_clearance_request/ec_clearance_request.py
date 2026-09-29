# Copyright (c) 2026, eCentric and contributors
"""EC Clearance Request - TU TAO khi Don nghi viec duyet xong (29/09/2026).

Cac ben (Line Manager / Operation / HR / HOF) ban giao SONG SONG (cap "Each Group" cua engine).
Noi dung la ban chup cua Don nghi viec da duyet - khong sua o day."""
import frappe
from frappe import _
from frappe.model.document import Document

_KHOA_SAU_KHI_GUI = ("resignation_request", "employee", "employee_name", "employee_email",
                     "last_working_day", "resignation_reason", "line_manager", "department")


class ECClearanceRequest(Document):
    def validate(self):
        self._snapshot_lock()

    def _snapshot_lock(self):
        if self.is_new() or not self.approval_request:
            return
        truoc = self.get_doc_before_save()
        if not truoc:
            return
        for f in _KHOA_SAU_KHI_GUI:
            if truoc.get(f) and truoc.get(f) != self.get(f):
                frappe.throw(_("Thông tin này chép từ Đơn nghỉ việc đã duyệt và không thể sửa ở đây."))
