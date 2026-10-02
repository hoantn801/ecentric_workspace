# Copyright (c) 2026, eCentric and contributors
"""/tong-quan#nhan-su/phan-bo: nut "Nhac" theo phong + "Nhac tat ca phong chua xong" - Hoan
02/10/2026. Du lieu: ecentric_workspace.hr.overview.api.remind_brand (chi HR_CARD_ROLES).
Chi dong bo lai trang; tu bat loi, khong chan deploy.
"""
import frappe

_MUST = ("ec-tq-bw-remind-v1", "remind_brand", "ec-tsclose-chotthay-v1", "ec-tq-sla-brand-v1")


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    from ecentric_workspace.hr.pages.tong_quan import page_sync
    try:
        res = page_sync.sync()
        frappe.logger("approval_center").info("p256 tong-quan: %s" % (res,))
        html = frappe.db.get_value("Web Page", {"route": page_sync.ROUTE}, "main_section_html") or ""
        miss = [m for m in _MUST if m not in html]
        if miss:
            frappe.log_error("p256: thieu %s" % (miss,), "p256 tong-quan KHONG toi noi")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p256 tong-quan sync failed")
