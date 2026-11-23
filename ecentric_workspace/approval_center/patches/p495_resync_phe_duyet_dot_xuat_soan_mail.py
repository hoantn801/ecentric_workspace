# Copyright (c) 2026, eCentric and contributors
"""p495_resync_phe_duyet_dot_xuat_soan_mail (23/11/2026, Hoan: "noi dung nen giong soan mail, approval
nay thay viec duyet qua mail cua CEO"): sync lai /approvals/adhoc-approval tu nguon repo (A65) - khung
soan kieu mail (Tu / Gui toi CEO / CC / Tieu de / Noi dung dinh dang). O soan la asset dung chung
ec_richtext.bundle.js (hooks web_include). Truong content_html do migrate them (DocType JSON).
Khoa chong troi: BASELINE moi, ban p491 trong SUPERSEDES. KHONG nem loi, KHONG xoa du lieu."""
import frappe

MOD = "ecentric_workspace.approval_center.features.adhoc_approval.infrastructure.page_sync"


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        res = frappe.get_module(MOD).sync() or {}
        frappe.logger("approval_center").info("p495 adhoc: %s" % res)
        if isinstance(res, dict) and res.get("action") == "refused":
            frappe.log_error("p495: adhoc-approval refused (live drift): %s" % res,
                             "p495_resync_phe_duyet_dot_xuat_soan_mail")
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "p495_resync_phe_duyet_dot_xuat_soan_mail failed")
