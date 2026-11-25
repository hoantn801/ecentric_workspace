# Copyright (c) 2026, eCentric and contributors
"""p558 (25/11/2026, anh Lam - EC-CTR-2026-00135, EC-DSR-2026-02797): cua so xem nhanh
/approvals/all-requests an nut "Duyet & Ky" va bao "dang cho cong xac nhan" khi buoc ky cua nguoi dang
xem dang bay (cung nguon platform.esign.service.in_flight_leg nhu form 27 p557).
Landmark: ec-apl-wait. Log, KHONG BAO GIO nem."""
import frappe

MOC = "ec-apl-wait"
_MOD = "ecentric_workspace.approval_center.ui.all_requests.page_sync"
_ROUTE = "approvals/all-requests"


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        res = frappe.get_module(_MOD).sync() or {}
        html = frappe.db.get_value("Web Page", {"route": _ROUTE}, "main_section_html") or ""
        frappe.logger("approval_center").info("p558: %s, dau moc %s" % (
            res.get("action"), "CO" if MOC in html else "THIEU"))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p558_resync_hub_cho_cong_ky")
