# Copyright (c) 2026, eCentric and contributors
"""24/11/2026 (PO): resync form 27 /approvals/contract-review - khoi "Bang tinh chi tiet" cua hop dong
KOL/KOC ve kieu BIEN LAI phang (ban B, bo kinh): [cam ve] + [thue] = gia tri hop dong / chi phi eCentric,
cong thuc ngay duoi so, chip loai HD + khau tru, ghi chu lam tron + nut tai .docx o hang cuoi.
Chi RESYNC trang (so lieu van do kol_calc dien giai). Lech / loi -> Error Log, KHONG nem (patch nem = migrate dung lai).
"""
import frappe

_MODULE = "ecentric_workspace.approval_center.features.contract_review.infrastructure.page_sync"
_ROUTE = "approvals/contract-review"
_MARKS = ("receiptHTML", "kol-rc-total", "kol-rc-foot", "calcLabel")


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        res = frappe.get_module(_MODULE).sync() or {}
        html = frappe.db.get_value("Web Page", {"route": _ROUTE}, "main_section_html") or ""
        thieu = [m for m in _MARKS if m not in html]
        frappe.logger("approval_center").info("p540 resync %s: %s (thieu moc: %s)"
                                              % (_ROUTE, res.get("action"), thieu or "khong"))
        if res.get("action") == "refused" or thieu:
            frappe.log_error(title="p540 resync %s" % _ROUTE, message="action=%r thieu=%r" % (res.get("action"), thieu))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p540 resync %s" % _ROUTE)
