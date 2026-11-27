# Copyright (c) 2026, eCentric and contributors
"""27/11/2026 (PO: mot cong ty / ho KD co nhieu KOL): resync form 27 /approvals/contract-review - sua creator
co danh sach "KOL / kenh cua creator" (cong ty / ho KD), phieu chon mot hay nhieu KOL (mot tong tien chung).
DocType EC Creator KOL / EC Contract Review KOL + truong Supplier.ec_cr_kols + kol_channels vao qua migrate
(JSON + fixtures); patch nay chi RESYNC trang. Lech / loi -> Error Log, KHONG nem (patch nem = migrate dung lai).
"""
import frappe

_MODULE = "ecentric_workspace.approval_center.features.contract_review.infrastructure.page_sync"
_ROUTE = "approvals/contract-review"
_MARKS = ("kolPickHTML", "kc-kol-add", "ec_cr_kols", "partner_sign_type", "signTypeOpts", "kol_open_online", "applyEsignWait", "doApproveAndSign",
          "partner_signer_identity")


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        res = frappe.get_module(_MODULE).sync() or {}
        html = frappe.db.get_value("Web Page", {"route": _ROUTE}, "main_section_html") or ""
        thieu = [m for m in _MARKS if m not in html]
        frappe.logger("approval_center").info("p587 resync %s: %s (thieu moc: %s)"
                                              % (_ROUTE, res.get("action"), thieu or "khong"))
        if res.get("action") == "refused" or thieu:
            frappe.log_error(title="p587 resync %s" % _ROUTE, message="action=%r thieu=%r" % (res.get("action"), thieu))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p587 resync %s" % _ROUTE)
