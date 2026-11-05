# Copyright (c) 2026, eCentric and contributors
"""Trang chu: card 'Phong hop' giua Truy cap nhanh va Chinh sach (05/11/2026, pm hotfix 10).
Dong bo Web Page trang chu tu nguon legacy_pages/home/main_section.html (page_sync co khoa lech).
Tu bat loi, khong chan deploy."""
import frappe


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        from ecentric_workspace.legacy_pages.home import page_sync
        res = page_sync.sync()
        frappe.logger("approval_center").info("p345_resync_home_phong_hop_v2 home: %s" % (res,))
        if isinstance(res, dict) and res.get("action") == "refused":
            frappe.log_error("p345_resync_home_phong_hop_v2: trang chu refused (live drift): %s" % (res,), "p345_resync_home_phong_hop_v2")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p345_resync_home_phong_hop_v2 failed")
