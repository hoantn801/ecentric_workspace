# Copyright (c) 2026, eCentric and contributors
"""/tong-quan#nhan-su/chot-cong: them bang "Leader chua chot team" + nut "CnB chot thay" -
Hoan 02/10/2026 (CnB can chot thay khi anh Lam chua chot cho cac truong phong).
Du lieu: ecentric_workspace.hr.timesheet_close.api.get_overview (leads) / close_for_lead.
Chi dong bo lai trang; tu bat loi, khong chan deploy.
"""
import frappe

_MUST = ("ec-tsclose-chotthay-v1", "close_for_lead", "ec-tq-sla-brand-v1")


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    from ecentric_workspace.hr.pages.tong_quan import page_sync
    try:
        res = page_sync.sync()
        frappe.logger("approval_center").info("p254 tong-quan: %s" % (res,))
        html = frappe.db.get_value("Web Page", {"route": page_sync.ROUTE}, "main_section_html") or ""
        miss = [m for m in _MUST if m not in html]
        if miss:
            frappe.log_error("p254: thieu %s" % (miss,), "p254 tong-quan KHONG toi noi")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p254 tong-quan sync failed")
