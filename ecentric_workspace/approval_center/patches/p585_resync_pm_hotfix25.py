# Copyright (c) 2026, eCentric and contributors
"""/pm hotfix 25 (27/11/2026: sua loi nho sau thiet ke lai: nut thao tac de ten nguoi giao, han lap ngay, ten quan ly): dong bo Web Page `project-management` tu nguon
pm/frontend/pm_app.html (page_sync co khoa lech). Tu bat loi, khong chan deploy."""
import frappe

_MUST = ('data-ec-shell="1"', "pm_redesign.js", "PMR.init")
_FORBID = ("__PMR_VER__",)


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    from ecentric_workspace.pm.frontend import page_sync
    try:
        res = page_sync.sync()
        frappe.logger("approval_center").info("p585_resync_pm_hotfix25 /pm hotfix25: %s" % (res,))
        if res.get("action") == "refused":
            frappe.log_error("p585_resync_pm_hotfix25: /pm refused (live drift): %s" % (res,), "p585_resync_pm_hotfix25")
            return
        html = frappe.db.get_value("Web Page", {"route": page_sync.ROUTE},
                                   "main_section_html") or ""
        miss = [m for m in _MUST if m not in html] + [m for m in _FORBID if m in html]
        if miss:
            frappe.log_error("p585_resync_pm_hotfix25: marker sai %s" % (miss,), "p585_resync_pm_hotfix25 KHONG toi noi")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p585_resync_pm_hotfix25 failed")
