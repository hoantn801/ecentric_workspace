# Copyright (c) 2026, eCentric and contributors
"""Hub "Cho toi xu ly": dai "Nhap cua toi" (05/09, Hoan feedback #1).

Bam "Luu nhap" xong khong thay phieu dau: ban nhap chua co EC Approval Request nen khong nam
trong tab nao. Gio tab "Cho toi xu ly" (trang dau) kem danh sach ban nhap cua chinh minh o
moi loai yeu cau da dang ky, gan nhan "Luu nhap", nut "Tiep tuc" mo lai form.
Backend: reporting.queries.fetch_my_drafts + service.my_drafts + api.list_requests(drafts).
Patch moi vi p142 da chay. Tu VERIFY landmark.
"""
import frappe

from ecentric_workspace.approval_center.ui.all_requests import page_sync

_LANDMARK = "function draftsHtml()"


def execute():
    res = page_sync.sync()
    frappe.log_error("p143 all_requests sync=%s" % (res or {}).get("action"), "p143 resync")
    html = frappe.db.get_value("Web Page", {"route": "approvals/all-requests"},
                               "main_section_html") or ""
    if _LANDMARK not in html:
        raise Exception("p143: hub van chua co dai Nhap cua toi sau sync (action=%s)"
                        % (res or {}).get("action"))
