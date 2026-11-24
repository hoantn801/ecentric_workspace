# Copyright (c) 2026, eCentric and contributors
"""p518_resync_home_the_phong_hop: card "Phong hop" o trang chu doi sang kieu danh sach
theo tang (phuong an A, Hoan duyet 24/11/2026): moi phong 1 dong ma + ten + suc chua +
cuoc hop hien tai/tiep theo, pill trang thai ben phai; bo thanh 08-19. Bump ?v cua
pm_home_calendar.js. Trang chu co khoa lech -> qua page_sync. Tu bat loi."""
import frappe


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    from ecentric_workspace.legacy_pages.home import page_sync
    try:
        res = page_sync.sync() or {}
        frappe.logger("approval_center").info("p518 home: %s" % (res,))
        if isinstance(res, dict) and res.get("action") == "refused":
            frappe.log_error("p518_resync_home_the_phong_hop: refused (live drift): %s" % (res,),
                             "p518_resync_home_the_phong_hop")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p518_resync_home_the_phong_hop failed")
