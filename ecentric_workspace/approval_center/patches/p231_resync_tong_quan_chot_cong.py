# Copyright (c) 2026, eCentric and contributors
"""/tong-quan#nhan-su: them tab "Chot cong" - Hoan 29/09/2026.

Tien do chot cong thang theo phong ban (da chot / dang chot / chua chot, leader con no) +
nut "Nhac" (chuong ERP + Teams toi nhan vien chua chot, leader con nguoi chua chot va
truong phong). Du lieu: ecentric_workspace.hr.timesheet_close.api.get_overview /
remind_department. Chi dong bo lai trang; tu bat loi, khong chan deploy.
"""
import frappe

_MUST = ("ec-tsclose-tq-v1", '["chot-cong", "Chốt công"]')


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    from ecentric_workspace.hr.pages.tong_quan import page_sync
    try:
        res = page_sync.sync()
        frappe.logger("approval_center").info("p231 tong-quan: %s" % (res,))
        html = frappe.db.get_value("Web Page", {"route": page_sync.ROUTE}, "main_section_html") or ""
        miss = [m for m in _MUST if m not in html]
        if miss:
            frappe.log_error("p231: thieu %s" % (miss,), "p231 tong-quan KHONG toi noi")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p231 tong-quan sync failed")
