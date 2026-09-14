# Copyright (c) 2026, eCentric and contributors
"""Contract Review: nut "Mo online" + canh bao tep doi sau khi duyet (14/09, Hoan).

Cung mot thay doi voi p185 nhung cho trang chi tiet rieng cua Contract Review. Hai trang deu
tu render danh sach dinh kem: `renderAttachments` bi chep y het trong 26 file
`features/*/ui/main_section.html`, va khung chi tiet cua hub la mot ban thu 27. Vi vay phan
TINH TOAN (link SharePoint + cap nao duyet truoc luc tep doi) dat o
`shared/requests/query_service.py` - mot cho, moi form co san; hai trang nay chi hien thi.

Landmark = dieu PHAI CO tren ban song sau khi sync."""
import frappe

from ecentric_workspace.approval_center.features.contract_review.infrastructure import page_sync

_LANDMARKS = ("sp_web_url", "canhBaoSuaSauDuyet")


def execute():
    res = page_sync.sync()
    action = (res or {}).get("action")
    frappe.log_error("p188 contract-review sync=%s" % action, "p188 resync")
    if action == "refused":
        frappe.log_error("p188: upsert TU CHOI GHI - trang KHONG duoc cap nhat.", "p188 REFUSED")
        return
    html = frappe.db.get_value("Web Page", {"route": "approvals/contract-review"},
                               "main_section_html") or ""
    thieu = [m for m in _LANDMARKS if m not in html]
    if thieu:
        frappe.log_error("p188: trang contract-review thieu dau moc %s" % thieu,
                         "p188 KHONG toi noi")
