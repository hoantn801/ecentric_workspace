# Copyright (c) 2026, eCentric and contributors
"""p491_resync_phe_duyet_dot_xuat_cc (23/11/2026, Hoan: "phe duyet dot xuat nen co them o cc nguoi"):
sync lai /approvals/adhoc-approval tu nguon repo (A65) - them o CC (nguoi theo doi, chon tu danh ba
noi bo). Truong cc_users do migrate tu them cot (DocType JSON). Co khoa chong troi: BASELINE moi,
ban cu nam trong SUPERSEDES. KHONG nem loi, KHONG xoa du lieu, KHONG goi ra ngoai."""
import frappe

MOD = "ecentric_workspace.approval_center.features.adhoc_approval.infrastructure.page_sync"


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        res = frappe.get_module(MOD).sync() or {}
        frappe.logger("approval_center").info("p491 adhoc: %s" % res)
        if isinstance(res, dict) and res.get("action") == "refused":
            frappe.log_error("p491: adhoc-approval refused (live drift): %s" % res,
                             "p491_resync_phe_duyet_dot_xuat_cc")
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "p491_resync_phe_duyet_dot_xuat_cc failed")
