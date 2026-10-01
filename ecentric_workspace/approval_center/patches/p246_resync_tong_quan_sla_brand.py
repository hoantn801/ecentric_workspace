# Copyright (c) 2026, eCentric and contributors
"""/tong-quan#nhan-su: them tab "SLA" va "Phan bo cong viec" cho CnB - Hoan 01/10/2026.

SLA ca cong ty theo phong / tung nguoi (cung cong thuc /sla) va tien do + ty trong phan bo
cong viec (brand weight) theo phong. Du lieu: ecentric_workspace.hr.overview.api.
get_sla_summary / get_brand_summary (chi HR_CARD_ROLES). Chi dong bo lai trang; tu bat loi,
khong chan deploy.
"""
import frappe

_MUST = ("ec-tq-sla-brand-v1", '["phan-bo", "Phân bổ công việc"]')


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    from ecentric_workspace.hr.pages.tong_quan import page_sync
    try:
        res = page_sync.sync()
        frappe.logger("approval_center").info("p246 tong-quan: %s" % (res,))
        html = frappe.db.get_value("Web Page", {"route": page_sync.ROUTE}, "main_section_html") or ""
        miss = [m for m in _MUST if m not in html]
        if miss:
            frappe.log_error("p246: thieu %s" % (miss,), "p246 tong-quan KHONG toi noi")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p246 tong-quan sync failed")
