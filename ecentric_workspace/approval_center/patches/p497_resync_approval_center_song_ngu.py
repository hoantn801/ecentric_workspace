# Copyright (c) 2026, eCentric and contributors
"""p497_resync_approval_center_song_ngu (23/11/2026, Hoan: "khong dep nhu mockup - song ngu, chu thich,
mau icon, mau the ghim, ngoi sao lech"): sync lai /approvals tu nguon repo (A65). Ten Viet + dong phu
Anh, icon to mau theo nhom, the ghim kieu mockup, sao canh giua dong tieu de. Du lieu ten Viet do p496
dien (chay TRUOC p497 trong patches.txt). Co khoa chong troi. KHONG nem loi, KHONG xoa du lieu."""
import frappe

MOD = "ecentric_workspace.approval_center.ui.hub.page_sync"


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        res = frappe.get_module(MOD).sync() or {}
        frappe.logger("approval_center").info("p497 hub: %s" % res)
        if isinstance(res, dict) and res.get("action") == "refused":
            frappe.log_error("p497: /approvals refused (live drift): %s" % res, "p497_resync_approval_center_song_ngu")
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "p497_resync_approval_center_song_ngu failed")
