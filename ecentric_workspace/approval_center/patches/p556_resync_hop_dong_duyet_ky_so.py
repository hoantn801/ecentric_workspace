# Copyright (c) 2026, eCentric and contributors
"""25/11/2026 (chi Lien EC-CTR-2026-00135: Duyet & Ky goi approve thuong): resync form 27 /approvals/contract-review -
nut Duyet & Ky cap ky so goi platform.esign.api.approve_and_sign (doApproveAndSign).
Chi RESYNC trang. Lech / loi -> Error Log, KHONG nem (patch nem = migrate dung lai).
"""
import frappe

_MODULE = "ecentric_workspace.approval_center.features.contract_review.infrastructure.page_sync"
_ROUTE = "approvals/contract-review"
_MARKS = ("doApproveAndSign", "laborSignHTML", "kol_make_sign_pdf", "partner_signer_identity", "kol_round_contract", "accSignable", "signPdfHTML")


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        res = frappe.get_module(_MODULE).sync() or {}
        html = frappe.db.get_value("Web Page", {"route": _ROUTE}, "main_section_html") or ""
        thieu = [m for m in _MARKS if m not in html]
        frappe.logger("approval_center").info("p556 resync %s: %s (thieu moc: %s)"
                                              % (_ROUTE, res.get("action"), thieu or "khong"))
        if res.get("action") == "refused" or thieu:
            frappe.log_error(title="p556 resync %s" % _ROUTE, message="action=%r thieu=%r" % (res.get("action"), thieu))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p556 resync %s" % _ROUTE)
