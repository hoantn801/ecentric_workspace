# Copyright (c) 2026, eCentric and contributors
"""EC Booking Request - CHI du lieu nghiep vu; TRANG THAI duyet nam o EC Approval Request.

Thay cho luong cu "brand bao Account -> Account nhan tin cho Booking": khong co ho so nao nen
khong ai do duoc SLA. Tu day moi yeu cau la mot phieu, co nguoi chiu trach nhiem va co han.

Luat nghiep vu (loai booking, khoang ngay hop le, tao brand moi) nam o
features/booking_request/application/service.py, khong nam day - controller chi khoa ban chup."""
import frappe
from frappe import _
from frappe.model.document import Document

#: Truong da di qua cap duyet: sua sau khi gui la xoa mat thu nguoi duyet da dong y.
_KHOA_SAU_KHI_GUI = ("department", "brand", "booking_type", "expected_budget",
                     "campaign_start_date", "booking_owner", "account_owner")


class ECBookingRequest(Document):
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
                frappe.throw(_("Trường này là bản chụp lúc gửi và không thể thay đổi sau khi gửi."))
