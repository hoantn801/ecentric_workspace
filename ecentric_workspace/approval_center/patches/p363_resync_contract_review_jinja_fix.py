# Copyright (c) 2026, eCentric and contributors
"""Hotfix 11/11/2026 22:00: form 27 Contract Review loi "417 Illegal template".

Ban p362 co mot dong JS chua hai dau ngoac nhon lien nhau -> Frappe coi main_section la Jinja,
roi tu choi vi trang co ".__" (`el.__ecw`). Nguon da bo chuoi do; patch nay chi RESYNC trang.
Gate moi: tests/standalone/test_page_jinja_safe.py.
"""
import frappe

_LANDMARKS = ("ContractReviewKOL", "kol_verify_signed", "BR:[")


def execute():
    """Chi RESYNC trang. Thanh cong ghi logger (khong ghi Error Log); lech / loi -> Error Log,
    KHONG BAO GIO nem (patch nem = ca lan migrate dung lai)."""
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        from ecentric_workspace.approval_center.features.contract_review.infrastructure import page_sync
        res = page_sync.sync() or {}
        html = frappe.db.get_value("Web Page", {"route": "approvals/contract-review"},
                                   "main_section_html") or ""
        thieu = [m for m in _LANDMARKS if m not in html]
        frappe.logger("approval_center").info("p363 contract_review resync: %s (thieu moc: %s)"
                                              % (res.get("action"), thieu or "khong"))
        if res.get("action") == "refused" or thieu:
            frappe.log_error(title="p363 resync contract_review",
                             message="action=%r thieu=%r" % (res.get("action"), thieu))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p363 resync contract_review")
