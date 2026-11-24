# Copyright (c) 2026, eCentric and contributors
"""24/11/2026 (PO): resync form 27 /approvals/contract-review - tab "Creator (mã MISA)" them nut Nhap file
(CSV / .xlsx) -> xem truoc tung dong -> xac nhan hang loat; Xuat CSV them cot ma_misa trong lam mau.
Chi RESYNC trang. Lech / loi -> Error Log, KHONG nem (patch nem = migrate dung lai).
"""
import frappe

_MODULE = "ecentric_workspace.approval_center.features.contract_review.infrastructure.page_sync"
_ROUTE = "approvals/contract-review"
_MARKS = ("kol-imp-file", "kol_misa_preview", "kol_misa_apply", "bindMisaImport")


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        res = frappe.get_module(_MODULE).sync() or {}
        html = frappe.db.get_value("Web Page", {"route": _ROUTE}, "main_section_html") or ""
        thieu = [m for m in _MARKS if m not in html]
        frappe.logger("approval_center").info("p522 resync %s: %s (thieu moc: %s)"
                                              % (_ROUTE, res.get("action"), thieu or "khong"))
        if res.get("action") == "refused" or thieu:
            frappe.log_error(title="p522 resync %s" % _ROUTE, message="action=%r thieu=%r" % (res.get("action"), thieu))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p522 resync %s" % _ROUTE)
