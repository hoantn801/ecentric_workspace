# Copyright (c) 2026, eCentric and contributors
"""/pm 09/11/2026: bump ?v= cua asset PM (pm_redesign / pm_rooms) de trinh duyet tai pm_rooms.js moi (sua "Invalid
Request" khi mo Phong hop; asset cache immutable 1 nam): dong bo Web Page `project-management` tu nguon
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
        frappe.logger("approval_center").info("p348_resync_pm_phong_hop_ver /pm phong hop ver: %s" % (res,))
        if res.get("action") == "refused":
            frappe.log_error("p348_resync_pm_phong_hop_ver: /pm refused (live drift): %s" % (res,), "p348_resync_pm_phong_hop_ver")
            return
        html = frappe.db.get_value("Web Page", {"route": page_sync.ROUTE},
                                   "main_section_html") or ""
        miss = [m for m in _MUST if m not in html] + [m for m in _FORBID if m in html]
        if miss:
            frappe.log_error("p348_resync_pm_phong_hop_ver: marker sai %s" % (miss,), "p348_resync_pm_phong_hop_ver KHONG toi noi")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p348_resync_pm_phong_hop_ver failed")
