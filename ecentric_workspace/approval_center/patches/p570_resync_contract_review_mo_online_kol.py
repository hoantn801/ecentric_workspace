# Copyright (c) 2026, eCentric and contributors
"""26/11/2026 (PO): resync form 27 /approvals/contract-review - khoi hop dong KOL/KOC co nut "Mo online (Word)"
(chi khi server tra `can_open_online` = nguoi duoc ban du + hop dong da co ban SharePoint thu muc han che);
bam -> POST kol_open_online (kiem quyen + ghi vet) -> mo tab moi. Nguoi duyet / CC van chi ban che.
Chi RESYNC trang. Lech / loi -> Error Log, KHONG nem (patch nem = migrate dung lai).
"""
import frappe

_MODULE = "ecentric_workspace.approval_center.features.contract_review.infrastructure.page_sync"
_ROUTE = "approvals/contract-review"
_MARKS = ("kol_open_online", "can_open_online", "openOnline", "data-kol=\"online\"")


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        res = frappe.get_module(_MODULE).sync() or {}
        html = frappe.db.get_value("Web Page", {"route": _ROUTE}, "main_section_html") or ""
        thieu = [m for m in _MARKS if m not in html]
        frappe.logger("approval_center").info("p570 resync %s: %s (thieu moc: %s)"
                                              % (_ROUTE, res.get("action"), thieu or "khong"))
        if res.get("action") == "refused" or thieu:
            frappe.log_error(title="p570 resync %s" % _ROUTE, message="action=%r thieu=%r" % (res.get("action"), thieu))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p570 resync %s" % _ROUTE)
