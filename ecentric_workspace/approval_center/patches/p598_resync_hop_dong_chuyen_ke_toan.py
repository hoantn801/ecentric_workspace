# Copyright (c) 2026, eCentric and contributors
"""27/11/2026 (chi Lien): resync form 27 /approvals/contract-review - nut "Chuyen cho ke toan khac" o buoc Ke toan
(application/finance_handover.py). Khong doi DocType; patch nay chi RESYNC trang. Lech / loi -> Error Log, KHONG nem.
"""
import frappe

_MODULE = "ecentric_workspace.approval_center.features.contract_review.infrastructure.page_sync"
_ROUTE = "approvals/contract-review"
_MARKS = ("doHandover", "handover_step", "kolPickHTML", "kc-kol-add", "ec_cr_kols", "partner_sign_type", "signTypeOpts", "kol_open_online", "applyEsignWait", "doApproveAndSign",
          "partner_signer_identity")


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        res = frappe.get_module(_MODULE).sync() or {}
        html = frappe.db.get_value("Web Page", {"route": _ROUTE}, "main_section_html") or ""
        thieu = [m for m in _MARKS if m not in html]
        frappe.logger("approval_center").info("p598 resync %s: %s (thieu moc: %s)"
                                              % (_ROUTE, res.get("action"), thieu or "khong"))
        if res.get("action") == "refused" or thieu:
            frappe.log_error(title="p598 resync %s" % _ROUTE, message="action=%r thieu=%r" % (res.get("action"), thieu))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p598 resync %s" % _ROUTE)
