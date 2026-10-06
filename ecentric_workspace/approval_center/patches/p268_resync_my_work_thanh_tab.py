# Copyright (c) 2026, eCentric and contributors
"""p268: tra lai thanh tab duoi cho /viec-cua-toi + cac gop y "Cho toi duyet" (07/10/2026, Hoan).

Thanh tab cua trang nay bi mat moi lan resync (p213, p264, p267) vi no tung duoc chen vao ban
live chu khong nam trong nguon. Tu nay page_sync.sync() tu gan lai (hr/pages/tab_bar.
insert_transform) - patch nay chi goi sync mot lan de ap. Tu kiem: co thanh tab + co khoi
Cho toi duyet. Loi chi ghi log."""
import frappe


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    from ecentric_workspace.action_center.pages.my_work import page_sync as my_work
    try:
        res = my_work.sync() or {}
        html = frappe.db.get_value("Web Page", {"route": my_work.ROUTE}, "main_section_html") or ""
        frappe.log_error(title="p268 viec-cua-toi thanh tab",
                         message="sync=%s thanh_tab=%s cho_duyet=%s" % (
                             res.get("action"), "ec-tabbar-shared-v1" in html, "data-ec-cho-duyet" in html))
    except Exception:
        frappe.log_error(title="p268_resync_my_work_thanh_tab", message=frappe.get_traceback())
