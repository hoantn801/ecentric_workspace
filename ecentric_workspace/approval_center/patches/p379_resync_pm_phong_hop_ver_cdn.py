# Copyright (c) 2026, eCentric and contributors
"""/pm 13/11/2026: doi ?v= lan nua - ban ?v=4e39feb225 bi CDN giu file pm_rooms.js CU (cache 1 nam,
yeu cau dau tien roi vao luc dang deploy). Dong bo Web Page `project-management` tu pm_app.html.
Tu bat loi, khong chan deploy."""
import frappe

_MUST = ('data-ec-shell="1"', "pm_redesign.js", "PMR.init")
_FORBID = ("__PMR_VER__",)


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    from ecentric_workspace.pm.frontend import page_sync
    try:
        res = page_sync.sync()
        frappe.logger("approval_center").info("p379_resync_pm_phong_hop_ver_cdn /pm phong hop ver cdn: %s" % (res,))
        if res.get("action") == "refused":
            frappe.log_error("p379_resync_pm_phong_hop_ver_cdn: /pm refused (live drift): %s" % (res,), "p379_resync_pm_phong_hop_ver_cdn")
            return
        html = frappe.db.get_value("Web Page", {"route": page_sync.ROUTE},
                                   "main_section_html") or ""
        miss = [m for m in _MUST if m not in html] + [m for m in _FORBID if m in html]
        if miss:
            frappe.log_error("p379_resync_pm_phong_hop_ver_cdn: marker sai %s" % (miss,), "p379_resync_pm_phong_hop_ver_cdn KHONG toi noi")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p379_resync_pm_phong_hop_ver_cdn failed")
