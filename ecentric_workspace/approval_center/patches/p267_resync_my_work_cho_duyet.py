# Copyright (c) 2026, eCentric and contributors
"""p267: dong bo /viec-cua-toi sau khi them khoi "Cho toi duyet" (06/10/2026).

Trang khong co after_migrate - byte tren site chi doi khi goi page_sync.sync() (xem p213).
my_work: repo so huu toan bo byte, khong khoa drift. Tu kiem landmark; loi chi ghi log."""
import frappe

_LANDMARK = "data-ec-cho-duyet"


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    from ecentric_workspace.action_center.pages.my_work import page_sync as my_work
    try:
        res = my_work.sync() or {}
        html = frappe.db.get_value("Web Page", {"route": my_work.ROUTE}, "main_section_html") or ""
        frappe.log_error(title="p267 viec-cua-toi cho duyet",
                         message="sync=%s landmark=%s" % (res.get("action"), _LANDMARK in html))
    except Exception:
        frappe.log_error(title="p267_resync_my_work_cho_duyet", message=frappe.get_traceback())
