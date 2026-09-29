# Copyright (c) 2026, eCentric and contributors
"""Trang chu: nut mo lai popup "Hom nay o eCentric" - PO Hoan 29/09/2026 16:32.

Da tich "Khong hien lai hom nay" thi mo lai bang dau? Nguon trang them nut ngay tren dai navy
(server ve san, trong dong ngay): ngay co sinh nhat -> chinh nhan sinh nhat bam duoc; ngay
khac ma popup co noi dung -> nut nho "Hom nay o eCentric". Bam = mo popup (ec_home_popup.js).

Chi goi legacy_pages.home.page_sync.sync() (khoa chong troi: live phai dang la ban p228
633e6dd0 hoac cac ban truoc; render thu Jinja truoc khi ghi). Tu bat loi, khong chan deploy.
"""
import frappe

_MUST = ("data-ec-today-open", "ec-today-pill")


def execute():
    from ecentric_workspace.legacy_pages.home import page_sync
    try:
        res = page_sync.sync()
        action = (res or {}).get("action")
        frappe.log_error("p230 home sync=%s" % action, "p230 trang chu nut mo lai popup")
        if action == "refused":
            frappe.log_error("p230: upsert TU CHOI GHI (khoa chong troi): %s" % (res,), "p230 REFUSED")
            return
        html = frappe.db.get_value("Web Page", {"route": page_sync.ROUTE}, "main_section_html") or ""
        miss = [m for m in _MUST if m not in html]
        if miss:
            frappe.log_error("p230: thieu %s" % (miss,), "p230 KHONG toi noi")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p230 home sync failed")
