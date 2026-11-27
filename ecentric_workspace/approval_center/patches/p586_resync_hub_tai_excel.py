# Copyright (c) 2026, eCentric and contributors
"""p582 (27/11/2026, Ke toan): trang /approvals/all-requests them nut "Excel" / "CSV" tren thanh
loc - tai TOAN BO ket qua cua tab + bo loc dang chon (reporting.api.export_requests, tran 5000
dong, ghi vet). Landmark: apl-xlsx. Log, KHONG BAO GIO nem."""
import frappe

MOC = 'id="apl-xlsx"'
_MOD = "ecentric_workspace.approval_center.ui.all_requests.page_sync"
_ROUTE = "approvals/all-requests"


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        res = frappe.get_module(_MOD).sync() or {}
        html = frappe.db.get_value("Web Page", {"route": _ROUTE}, "main_section_html") or ""
        frappe.logger("approval_center").info("p582: %s, dau moc %s" % (
            res.get("action"), "CO" if MOC in html else "THIEU"))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p586_resync_hub_tai_excel")
