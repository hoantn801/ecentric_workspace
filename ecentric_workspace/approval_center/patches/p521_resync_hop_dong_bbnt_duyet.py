# Copyright (c) 2026, eCentric and contributors
"""24/11/2026 (PO chot C): resync form 27 /approvals/contract-review - BBNT tung dot co chuoi duyet rieng:
nut "Gui duyet" / "Gui duyet lai", trang thai duyet cua dot, chi tai ban ky khi dot da duyet xong, mo trang
tu link phieu dot (?id=EC-BBNT-... -> hop dong, to sang dong cua dot).
Chi RESYNC trang. Lech / loi -> Error Log, KHONG nem (patch nem = migrate dung lai).
"""
import frappe

_MODULE = "ecentric_workspace.approval_center.features.contract_review.infrastructure.page_sync"
_ROUTE = "approvals/contract-review"
_MARKS = ("signPdfHTML", "LEVELS_LABOR", "kol_round_contract", "accSignable")


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        res = frappe.get_module(_MODULE).sync() or {}
        html = frappe.db.get_value("Web Page", {"route": _ROUTE}, "main_section_html") or ""
        thieu = [m for m in _MARKS if m not in html]
        frappe.logger("approval_center").info("p521 resync %s: %s (thieu moc: %s)"
                                              % (_ROUTE, res.get("action"), thieu or "khong"))
        if res.get("action") == "refused" or thieu:
            frappe.log_error(title="p521 resync %s" % _ROUTE, message="action=%r thieu=%r" % (res.get("action"), thieu))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p521 resync %s" % _ROUTE)
