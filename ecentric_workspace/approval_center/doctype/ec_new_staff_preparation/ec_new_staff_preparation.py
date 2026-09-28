# Copyright (c) 2026, eCentric and contributors
"""EC New Staff Preparation - TU TAO khi Offer Request duyet xong (28/09/2026).

Cac ben (Lead HR / HOF / CnB / Operation) chuan bi SONG SONG (cap "Each Group" cua engine).
Noi dung chep tu Offer - KHONG co muc luong. Chi `welcome_intro` va `onboard_date` duoc HR
chinh sau khi gui (qua endpoint rieng); phan con lai la ban chup cua Offer da duyet."""
import frappe
from frappe import _
from frappe.model.document import Document

_KHOA_SAU_KHI_GUI = ("offer_request", "hiring_request", "candidate_name", "position",
                     "line_manager", "department", "company_laptop", "mobile_phone",
                     "probation_end_date", "note")


class ECNewStaffPreparation(Document):
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
                frappe.throw(_("Thông tin này chép từ Offer đã duyệt và không thể sửa ở đây."))
