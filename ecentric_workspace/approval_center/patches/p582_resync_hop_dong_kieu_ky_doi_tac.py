# Copyright (c) 2026, eCentric and contributors
"""27/11/2026 (PO: KOL hay chi ky anh): resync form 27 /approvals/contract-review - khoi "Nguoi ky phia
doi tac" co o chon "Kieu ky cua doi tac" (Ky anh / USB Token / eSign / VNeID / eKYC; trong = mac dinh
cua cong). Truong `partner_sign_type` vao DocType qua migrate (JSON), patch nay chi RESYNC trang.
Lech / loi -> Error Log, KHONG nem (patch nem = migrate dung lai).
"""
import frappe

_MODULE = "ecentric_workspace.approval_center.features.contract_review.infrastructure.page_sync"
_ROUTE = "approvals/contract-review"
_MARKS = ("partner_sign_type", "signTypeOpts", "kol_open_online", "applyEsignWait", "doApproveAndSign",
          "partner_signer_identity")


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        res = frappe.get_module(_MODULE).sync() or {}
        html = frappe.db.get_value("Web Page", {"route": _ROUTE}, "main_section_html") or ""
        thieu = [m for m in _MARKS if m not in html]
        frappe.logger("approval_center").info("p582 resync %s: %s (thieu moc: %s)"
                                              % (_ROUTE, res.get("action"), thieu or "khong"))
        if res.get("action") == "refused" or thieu:
            frappe.log_error(title="p582 resync %s" % _ROUTE, message="action=%r thieu=%r" % (res.get("action"), thieu))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p582 resync %s" % _ROUTE)
