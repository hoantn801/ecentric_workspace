# Copyright (c) 2026, eCentric and contributors
"""15/11/2026: resync de nghi thanh toan /approvals/payment-request - QC dem 15/11:
  * C6: mo sua phieu A (nguon DNMH) roi phieu B (nguon hop dong KOL) trong cung trang thi nap lai
    danh sach chung tu theo loai nguon cua B (truoc do giu danh sach cua A, o chon thieu hop dong).
  * C12: nhan so du nguon "da thanh toan" -> "da de nghi chi" (so tinh ca phieu chua chi).
Chi RESYNC trang. Lech / loi -> Error Log, KHONG nem (patch nem = migrate dung lai).
"""
import frappe

_ROUTE = "approvals/payment-request"
_MARKS = ("_fundRowsFor", "đã đề nghị chi")


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        mod = frappe.get_module(
            "ecentric_workspace.approval_center.features.payment_request.infrastructure.page_sync")
        res = mod.sync() or {}
        html = frappe.db.get_value("Web Page", {"route": _ROUTE}, "main_section_html") or ""
        thieu = [m for m in _MARKS if m not in html]
        frappe.logger("approval_center").info("p382 resync %s: %s (thieu moc: %s)"
                                              % (_ROUTE, res.get("action"), thieu or "khong"))
        if res.get("action") == "refused" or thieu:
            frappe.log_error(title="p382 resync %s" % _ROUTE, message="action=%r thieu=%r" % (res.get("action"), thieu))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p382 resync %s" % _ROUTE)
