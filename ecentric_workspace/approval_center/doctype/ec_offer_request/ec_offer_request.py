# Copyright (c) 2026, eCentric and contributors
"""EC Offer Request - CHI du lieu nghiep vu; TRANG THAI duyet nam o EC Approval Request.

Mot Hiring Request da duyet -> HR tuyen dung chot duoc ung vien -> lap Offer (28/09/2026).
Luat nghiep vu (ai duoc tao, chep ban chup tu Hiring, kiem ngay) nam o
features/offer_request/application/service.py; controller chi khoa ban chup."""
import frappe
from frappe import _
from frappe.model.document import Document

#: Ban chup tu Hiring. Line manager la NGUOI DUYET CAP 1 - sua sau khi gui la doi nguoi duyet.
_KHOA_SAU_KHI_GUI = ("hiring_request", "position", "employment_type", "line_manager", "department")


class ECOfferRequest(Document):
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
                frappe.throw(_("Trường này là bản chụp từ Hiring Request lúc gửi và không thể thay đổi."))
