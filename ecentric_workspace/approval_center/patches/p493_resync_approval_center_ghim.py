# Copyright (c) 2026, eCentric and contributors
"""p493_resync_approval_center_ghim (23/11/2026, Hoan chon mockup A): sync lai /approvals tu nguon repo
(A65) - khoi "Da ghim" + "Ban hay dung", thanh tim + chip MOT dong, tim khong dau, the chua dung duoc
gom cuoi. DocType EC Approval Type Pin do migrate tao. Co khoa chong troi (BASELINE moi, ban cu trong
SUPERSEDES - live do 23/11 = 2d6ce1fa, khop). KHONG nem loi, KHONG xoa du lieu, KHONG goi ra ngoai."""
import frappe

MOD = "ecentric_workspace.approval_center.ui.hub.page_sync"


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        res = frappe.get_module(MOD).sync() or {}
        frappe.logger("approval_center").info("p493 hub: %s" % res)
        if isinstance(res, dict) and res.get("action") == "refused":
            frappe.log_error("p493: /approvals refused (live drift): %s" % res, "p493_resync_approval_center_ghim")
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "p493_resync_approval_center_ghim failed")
