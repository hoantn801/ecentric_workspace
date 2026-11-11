# Copyright (c) 2026, eCentric and contributors
"""12/11/2026: hop dong KOL dung lai 18 mau HDDV/BBNT cua Ke toan (tool Google Sheet cu).

Nguon trang doi: bo bang nhan placeholder {{...}} cu (nhan "con thieu" do server dich),
o so ngay thanh toan de trong = mac dinh theo loai creator. Patch nay chi RESYNC trang.
Truong moi `platform` cua EC Contract Template di theo migrate DocType, khong can patch du lieu
(chua co mau nao tren site).
"""
import frappe

_LANDMARKS = ("ContractReviewKOL", "kol_verify_signed", "missing_labels", "Mặc định theo loại creator")


def execute():
    """Chi RESYNC trang. Lech / loi -> Error Log, KHONG BAO GIO nem (patch nem = migrate dung lai)."""
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        from ecentric_workspace.approval_center.features.contract_review.infrastructure import page_sync
        res = page_sync.sync() or {}
        html = frappe.db.get_value("Web Page", {"route": "approvals/contract-review"},
                                   "main_section_html") or ""
        thieu = [m for m in _LANDMARKS if m not in html]
        frappe.logger("approval_center").info("p364 contract_review resync: %s (thieu moc: %s)"
                                              % (res.get("action"), thieu or "khong"))
        if res.get("action") == "refused" or thieu:
            frappe.log_error(title="p364 resync contract_review",
                             message="action=%r thieu=%r" % (res.get("action"), thieu))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p364 resync contract_review")
