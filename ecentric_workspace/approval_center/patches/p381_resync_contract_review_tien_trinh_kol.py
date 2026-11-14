# Copyright (c) 2026, eCentric and contributors
"""15/11/2026: resync form 27 /approvals/contract-review - thanh tien trinh hop dong KOL noi them
Ky HD -> Nghiem thu -> Thanh toan, the "Ky hop dong" / "Nghiem thu" hien mo truoc khi toi buoc
(PO 12/11), ghi "Duyet thay boi ..." khi System Manager duyet thay mot cap.
Chi RESYNC trang. Lech / loi -> Error Log, KHONG nem (patch nem = migrate dung lai).
"""
import frappe

_ROUTE = "approvals/contract-review"
_MARKS = ("lifeSteps", "kol-later", "Duyệt thay bởi")


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        mod = frappe.get_module(
            "ecentric_workspace.approval_center.features.contract_review.infrastructure.page_sync")
        res = mod.sync() or {}
        html = frappe.db.get_value("Web Page", {"route": _ROUTE}, "main_section_html") or ""
        thieu = [m for m in _MARKS if m not in html]
        frappe.logger("approval_center").info("p381 resync %s: %s (thieu moc: %s)"
                                              % (_ROUTE, res.get("action"), thieu or "khong"))
        if res.get("action") == "refused" or thieu:
            frappe.log_error(title="p381 resync %s" % _ROUTE, message="action=%r thieu=%r" % (res.get("action"), thieu))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p381 resync %s" % _ROUTE)
