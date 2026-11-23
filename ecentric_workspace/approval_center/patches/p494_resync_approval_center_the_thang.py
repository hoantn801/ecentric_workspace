# Copyright (c) 2026, eCentric and contributors
"""p494_resync_approval_center_the_thang (23/11/2026, Hoan bao "trong lech lech"): sync lai /approvals
tu nguon repo (A65). The dung lop card-main (lop body cua Bootstrap co padding 1.25rem day noi dung
lech), tieu de khoi Da ghim / Ban hay dung la div (theme web dinh kieu h2), "da gui N lan" khong xuong
dong; lan dau mo trang goi seed_default_pins (ghim san 4 loai). Khoa chong troi: BASELINE moi, ban
p493 trong SUPERSEDES. KHONG nem loi, KHONG xoa du lieu, KHONG goi ra ngoai."""
import frappe

MOD = "ecentric_workspace.approval_center.ui.hub.page_sync"


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        res = frappe.get_module(MOD).sync() or {}
        frappe.logger("approval_center").info("p494 hub: %s" % res)
        if isinstance(res, dict) and res.get("action") == "refused":
            frappe.log_error("p494: /approvals refused (live drift): %s" % res, "p494_resync_approval_center_the_thang")
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "p494_resync_approval_center_the_thang failed")
