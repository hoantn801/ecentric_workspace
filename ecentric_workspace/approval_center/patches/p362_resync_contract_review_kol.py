# Copyright (c) 2026, eCentric and contributors
"""Contract Review: khoi hop dong KOL/KOC + tab Creator cho ke toan (11/11/2026).

Plan "Hop dong KOL/KOC len ERP" giai doan 1-3+5: chon SO doanh thu (SO GBS qua SO doi ung),
chon / tao creator (chan trung), so tien do server tinh, tao hop dong tu mau .docx, AI QC,
xac nhan ky, cac dot BBNT va tran chi cho DNTT.

Landmark = dieu PHAI CO tren ban song sau khi sync."""
import frappe

_LANDMARKS = ("ContractReviewKOL", "kol_preview_amounts", "Creator (mã MISA)", "kol_delete_acceptance")


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
        frappe.logger("approval_center").info("p362 contract_review resync: %s (thieu moc: %s)"
                                              % (res.get("action"), thieu or "khong"))
        if res.get("action") == "refused" or thieu:
            frappe.log_error(title="p362 resync contract_review",
                             message="action=%r thieu=%r" % (res.get("action"), thieu))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p362 resync contract_review")
