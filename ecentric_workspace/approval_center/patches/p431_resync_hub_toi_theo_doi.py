# Copyright (c) 2026, eCentric and contributors
"""p431 (23/11/2026, Dot 0 HR): trang /approvals/all-requests them tab "Tôi theo dõi"
(box=watching - phieu minh la nguoi theo doi, participant_purpose=Notify).
Landmark: data-box="watching". Log, KHONG BAO GIO nem."""
import frappe

MOC = 'data-box="watching"'
_MOD = "ecentric_workspace.approval_center.ui.all_requests.page_sync"
_ROUTE = "approvals/all-requests"


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        res = frappe.get_module(_MOD).sync() or {}
        html = frappe.db.get_value("Web Page", {"route": _ROUTE}, "main_section_html") or ""
        frappe.logger("approval_center").info("p431: %s, dau moc %s" % (
            res.get("action"), "CO" if MOC in html else "THIEU"))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p431_resync_hub_toi_theo_doi")
