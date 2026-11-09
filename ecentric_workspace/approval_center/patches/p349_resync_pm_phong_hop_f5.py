# Copyright (c) 2026, eCentric and contributors
"""/pm 09/11/2026: bump ?v= lan 2 - pm_rooms.js cho ecApi khi tai lai trang (F5) de khong bat hop thoai
"Invalid Request": dong bo Web Page `project-management` tu nguon pm/frontend/pm_app.html (page_sync co khoa
lech). Tu bat loi, khong chan deploy."""
import frappe

_MUST = ('data-ec-shell="1"', "pm_redesign.js", "PMR.init")
_FORBID = ("__PMR_VER__",)


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    from ecentric_workspace.pm.frontend import page_sync
    try:
        res = page_sync.sync()
        frappe.logger("approval_center").info("p349_resync_pm_phong_hop_f5 /pm phong hop f5: %s" % (res,))
        if res.get("action") == "refused":
            frappe.log_error("p349_resync_pm_phong_hop_f5: /pm refused (live drift): %s" % (res,), "p349_resync_pm_phong_hop_f5")
            return
        html = frappe.db.get_value("Web Page", {"route": page_sync.ROUTE},
                                   "main_section_html") or ""
        miss = [m for m in _MUST if m not in html] + [m for m in _FORBID if m in html]
        if miss:
            frappe.log_error("p349_resync_pm_phong_hop_f5: marker sai %s" % (miss,), "p349_resync_pm_phong_hop_f5 KHONG toi noi")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p349_resync_pm_phong_hop_f5 failed")
