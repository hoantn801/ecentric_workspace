# Copyright (c) 2026, eCentric and contributors
"""/pm hotfix 19 (18/11/2026: doi ten viec tai cho trong chi tiet viec + ngan Viec can lam; doi ?v=): dong bo Web Page `project-management` tu nguon
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
        frappe.logger("approval_center").info("p418_resync_pm_hotfix19 /pm hotfix19: %s" % (res,))
        if res.get("action") == "refused":
            frappe.log_error("p418_resync_pm_hotfix19: /pm refused (live drift): %s" % (res,), "p418_resync_pm_hotfix19")
            return
        html = frappe.db.get_value("Web Page", {"route": page_sync.ROUTE},
                                   "main_section_html") or ""
        miss = [m for m in _MUST if m not in html] + [m for m in _FORBID if m in html]
        if miss:
            frappe.log_error("p418_resync_pm_hotfix19: marker sai %s" % (miss,), "p418_resync_pm_hotfix19 KHONG toi noi")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p418_resync_pm_hotfix19 failed")
