# Copyright (c) 2026, eCentric and contributors
"""Resync hub: nut "Ket noi SCTS" khong con doi phai co san anh xa.

Dieu kien cu (`needs_link && has_mapping`) an nut voi dung nhom can no nhat: nguoi CHUA TUNG
ket noi thi chua co dong `EC SCTS User Mapping` nao, nen khong thay nut - va khong co mot
dong chu nao noi vi sao. Tam (tam.nguyen, tao tai khoan SCTS 09/09) bao "tren ERP khong co
nut ket noi SCTS" dung vi the.

Tu nay `user_link.link()` dang nhap TRUOC roi tu dung anh xa tu chinh phan hoi cua SCTS, nen
khong con gi de doi.

Patch moi vi cac patch resync hub truoc do (p162/p164, va p168 cua chat khac) da chay -
patch chay MOT LAN, khong bao gio tro lai patch cu.
"""
import frappe

from ecentric_workspace.approval_center.ui.hub import page_sync as hub_sync

#: Dau vet cua ban MOI tren trang song. Sync bao "da ghi" ma trang van la ban cu thi phai
#: biet ngay o day, dung doi toi luc nguoi dung khong thay nut.
_EXPECT = ("st && st.needs_link)",)
#: Dieu kien cu - con lai tuc la sync khong toi noi.
_FORBID = ("st.needs_link && st.has_mapping",)


def execute():
    try:
        res = hub_sync.sync()
        frappe.log_error("p169 hub sync=%s" % (res or {}).get("action"), "p169 resync")
        html = frappe.db.get_value("Web Page", {"route": "approvals"}, "main_section_html") or ""
        missing = [m for m in _EXPECT if m not in html]
        left = [m for m in _FORBID if m in html]
        if missing or left:
            frappe.log_error("p169: thieu=%s con_lai=%s" % (missing, left), "p169 resync KHONG toi noi")
    except Exception:
        # Patch chay trong migrate: mot exception lam chet ca lan deploy (bai hoc p116).
        frappe.log_error(frappe.get_traceback(), "p169 resync failed")
