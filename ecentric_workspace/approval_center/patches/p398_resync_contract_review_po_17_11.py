# Copyright (c) 2026, eCentric and contributors
"""17/11/2026: resync form 27 /approvals/contract-review - quyet dinh PO 17/11: tai ban du thong tin
creator qua POST co ghi vet (chi nguoi tao creator + Ke toan), ban xem da che cho nguoi duyet, canh bao
STK creator doi + Ke toan xac nhan, nut Thanh ly hop dong, KOL khong chon "dieu chinh", Ke toan sua
ten / loai creator, nut "Tao phieu moi tu phieu nay".
Chi RESYNC trang. Lech / loi -> Error Log, KHONG nem (patch nem = migrate dung lai).
"""
import frappe

_ROUTE = "approvals/contract-review"
_MARKS = ("kol_download_file", "payeeok", "closehd", "data-act=\"clone\"", "lockIdentity")


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        mod = frappe.get_module(
            "ecentric_workspace.approval_center.features.contract_review.infrastructure.page_sync")
        res = mod.sync() or {}
        html = frappe.db.get_value("Web Page", {"route": _ROUTE}, "main_section_html") or ""
        thieu = [m for m in _MARKS if m not in html]
        frappe.logger("approval_center").info("p398 resync %s: %s (thieu moc: %s)"
                                              % (_ROUTE, res.get("action"), thieu or "khong"))
        if res.get("action") == "refused" or thieu:
            frappe.log_error(title="p398 resync %s" % _ROUTE, message="action=%r thieu=%r" % (res.get("action"), thieu))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p398 resync %s" % _ROUTE)
