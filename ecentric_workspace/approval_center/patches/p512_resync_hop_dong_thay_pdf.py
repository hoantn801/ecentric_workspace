# Copyright (c) 2026, eCentric and contributors
"""24/11/2026 (PR-H): resync form 27 /approvals/contract-review - "Thay ban PDF" khi phieu "Can bo sung" ma goi ky
da khoa: hoi xac nhan -> reopen_signing_setup (PR-G) TRUOC khi tai ban moi.
Chi RESYNC trang. Lech / loi -> Error Log, KHONG nem (patch nem = migrate dung lai).
"""
import frappe

_MODULE = "ecentric_workspace.approval_center.features.contract_review.infrastructure.page_sync"
_ROUTE = "approvals/contract-review"
_MARKS = ("signPdfHTML", "kol_attach_sign_pdf", "reopen_signing_setup")


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        res = frappe.get_module(_MODULE).sync() or {}
        html = frappe.db.get_value("Web Page", {"route": _ROUTE}, "main_section_html") or ""
        thieu = [m for m in _MARKS if m not in html]
        frappe.logger("approval_center").info("p512 resync %s: %s (thieu moc: %s)"
                                              % (_ROUTE, res.get("action"), thieu or "khong"))
        if res.get("action") == "refused" or thieu:
            frappe.log_error(title="p512 resync %s" % _ROUTE, message="action=%r thieu=%r" % (res.get("action"), thieu))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p512 resync %s" % _ROUTE)
