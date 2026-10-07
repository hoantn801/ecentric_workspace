# Copyright (c) 2026, eCentric and contributors
"""/tong-quan#nhan-su: tab SLA va Phan bo cong viec them nut "File tong hop thang" -
Hoan 07/10/2026 (ec-cnb-dashboard-v1). CnB tai mot file 4 sheet dung mau file
"Timesheet Thang N Dashboard" ho dang ghep tay moi thang.
Du lieu: ecentric_workspace.hr.overview.api.export_summary_xlsx?kind=cnb.
Chi dong bo lai trang; tu bat loi, khong chan deploy.
"""
import frappe

_MUST = ("ec-cnb-dashboard-v1", "kind=cnb", "ec-tq-sla-brand-v1")


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    from ecentric_workspace.hr.pages.tong_quan import page_sync
    try:
        res = page_sync.sync()
        frappe.logger("approval_center").info("p273 tong-quan: %s" % (res,))
        html = frappe.db.get_value("Web Page", {"route": page_sync.ROUTE}, "main_section_html") or ""
        miss = [m for m in _MUST if m not in html]
        if miss:
            frappe.log_error("p273: thieu %s" % (miss,), "p273 tong-quan KHONG toi noi")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p273 tong-quan sync failed")
