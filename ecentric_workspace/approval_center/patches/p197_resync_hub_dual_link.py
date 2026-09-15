# Copyright (c) 2026, eCentric and contributors
"""Hub: the dinh kem kem mot the nho "ban ERP" ben canh (15/09, Hoan).

Cung ly do voi p196 nhung cho khung chi tiet dung chung cua /approvals/all-requests: SharePoint
chan mot nguoi thi ho van phai doc duoc ho so. Xem chu thich dai o p196."""
import frappe

from ecentric_workspace.approval_center.ui.all_requests import page_sync

_LANDMARKS = ("ec-apl-alt", "ban ERP")


def execute():
    res = page_sync.sync()
    action = (res or {}).get("action")
    frappe.log_error("p197 all-requests sync=%s" % action, "p197 resync")
    if action == "refused":
        frappe.log_error("p197: upsert TU CHOI GHI - trang KHONG duoc cap nhat.", "p197 REFUSED")
        return
    html = frappe.db.get_value("Web Page", {"route": "approvals/all-requests"},
                               "main_section_html") or ""
    thieu = [m for m in _LANDMARKS if m not in html]
    if thieu:
        frappe.log_error("p197: trang all-requests thieu dau moc %s" % thieu,
                         "p197 KHONG toi noi")
