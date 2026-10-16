# Copyright (c) 2026, eCentric and contributors
"""Ban doi chung: ban chup BAT BIEN cua tep hop dong tren SharePoint tai moi quyet dinh duyet.

VI SAO CAN (16/10/2026, Finance bao, PO Hoan duyet phuong an A). Nguoi duyet sua ban SONG tren
Word Online o che do track changes. Nguoi duyet sau co the Accept/Reject thay doi hay xoa
comment cua nguoi truoc - va cong suc cua nguoi truoc bien mat, khong con dau vet nao cho biet
ho da thay gi, da sua gi. Ban ghi nay giu lai CHINH XAC tep trong trang thai luc bam nut.

BAT BIEN. Sau khi tao, cac truong bang chung (tep, sha256, eTag, quyet dinh) khong sua duoc -
ke ca qua Desk. Quyen DocType chi cho System Manager doc/xoa; nguoi dung xem qua man hinh chi
tiet phieu (da qua cong `can_view`), con tep thi gan vao phieu nghiep vu nen di dung luat quyen
cua dinh kem hien co.
"""
import frappe
from frappe import _
from frappe.model.document import Document

#: Nhung truong lam nen bang chung. Doi bat ky truong nao sau khi tao = gia mao ban chup.
TRUONG_BANG_CHUNG = (
    "khoa", "business_doctype", "business_name", "approval_request", "approval_action",
    "level_no", "actor", "action", "action_time", "captured_at", "sp_item_id", "sp_etag",
    "sp_version_id", "sp_last_modified", "docx_file", "docx_file_url", "sha256",
    "pdf_file", "pdf_file_url",
)


class ECSharePointSnapshot(Document):
    def validate(self):
        if self.is_new():
            return
        truoc = self.get_doc_before_save()
        if not truoc:
            return
        doi = [f for f in TRUONG_BANG_CHUNG if str(truoc.get(f) or "") != str(self.get(f) or "")]
        if doi:
            frappe.throw(_("Bản đối chứng là bằng chứng bất biến — không được sửa: {0}").format(
                ", ".join(doi)), frappe.PermissionError)
