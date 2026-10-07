# Copyright (c) 2026, eCentric and contributors
"""/pm ve nguon (A65): dong bo Web Page `project-management` tu
pm/frontend/pm_app.html qua page_sync co khoa lech. Thay the duong
transform tren live cua p272. Tu bat loi, khong chan deploy."""
import frappe

_MUST = ('data-ec-shell="1"', 'head==="new"')
_FORBID = ('id="ec-pm-nav-bridge"', '<style id="ec-pm-shell-grid">')


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    from ecentric_workspace.pm.frontend import page_sync
    try:
        res = page_sync.sync()
        frappe.logger("approval_center").info("p275_resync_pm_vao_nguon /pm ve nguon: %s" % (res,))
        if res.get("action") == "refused":
            frappe.log_error("p275_resync_pm_vao_nguon: /pm refused (live drift): %s" % (res,), "p275_resync_pm_vao_nguon")
            return
        html = frappe.db.get_value("Web Page", {"route": page_sync.ROUTE},
                                   "main_section_html") or ""
        miss = [m for m in _MUST if m not in html] + [m for m in _FORBID if m in html]
        if miss:
            frappe.log_error("p275_resync_pm_vao_nguon: marker sai %s" % (miss,), "p275_resync_pm_vao_nguon KHONG toi noi")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p275_resync_pm_vao_nguon failed")
