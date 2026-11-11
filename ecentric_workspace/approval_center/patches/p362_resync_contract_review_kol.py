# Copyright (c) 2026, eCentric and contributors
"""Contract Review: khoi hop dong KOL/KOC + tab Creator cho ke toan (11/11/2026).

Plan "Hop dong KOL/KOC len ERP" giai doan 1-3+5: chon SO doanh thu (SO GBS qua SO doi ung),
chon / tao creator (chan trung), so tien do server tinh, tao hop dong tu mau .docx, AI QC,
xac nhan ky, cac dot BBNT va tran chi cho DNTT.

Landmark = dieu PHAI CO tren ban song sau khi sync."""
import frappe

from ecentric_workspace.approval_center.features.contract_review.infrastructure import page_sync

_LANDMARKS = ("ContractReviewKOL", "kol_preview_amounts", "Creator (mã MISA)")


def execute():
    res = page_sync.sync()
    action = (res or {}).get("action")
    frappe.log_error("p362 contract-review sync=%s" % action, "p362 resync")
    if action == "refused":
        frappe.log_error("p362: upsert TU CHOI GHI - trang KHONG duoc cap nhat.", "p362 REFUSED")
        return
    html = frappe.db.get_value("Web Page", {"route": "approvals/contract-review"},
                               "main_section_html") or ""
    thieu = [m for m in _LANDMARKS if m not in html]
    if thieu:
        frappe.log_error("p362: trang contract-review thieu dau moc %s" % thieu,
                         "p362 KHONG toi noi")
