# Copyright (c) 2026, eCentric and contributors
"""EC Employee Review - CHI du lieu nghiep vu; TRANG THAI duyet nam o EC Approval Request.

Luat (nguon ngay, Dieu 20 / 25, an nhan xet LM, nhap tu gui) nam o
features/employee_review/{domain,application}. Controller chi khoa ban chup: doi tuong + dong
hop dong da di qua cap duyet thi khong doi duoc nua."""
import frappe
from frappe import _
from frappe.model.document import Document

#: Ban chup luc gui: sua sau khi gui la danh gia mot nguoi / mot hop dong khac voi cai cac cap
#: da xem.
_KHOA_SAU_KHI_GUI = ("review_type", "nhan_vien", "employee_user", "dong_hop_dong", "hd_tu_ngay",
                     "hd_den_ngay", "loai_hop_dong", "tieu_chi_json")


class ECEmployeeReview(Document):
    def validate(self):
        self._snapshot_lock()
        self._title_lock()

    def _title_lock(self):
        """Tieu de tuy chinh chi sua o NHAP (Hoan chot 23/11) - ke ca tu rong -> co gia tri, moi
        duong ghi (Desk, API, job). Quyen C&B kiem o service.prepare_draft."""
        if self.is_new() or not self.approval_request:
            return
        truoc = self.get_doc_before_save()
        if truoc and (truoc.get("custom_title") or "") != (self.get("custom_title") or ""):
            frappe.throw(_("Phiếu đã gửi - không sửa tiêu đề được nữa."))

    def _snapshot_lock(self):
        if self.is_new() or not self.approval_request:
            return
        truoc = self.get_doc_before_save()
        if not truoc:
            return
        for f in _KHOA_SAU_KHI_GUI:
            if truoc.get(f) and truoc.get(f) != self.get(f):
                frappe.throw(_("Trường này là bản chụp lúc gửi và không thể thay đổi sau khi gửi."))
