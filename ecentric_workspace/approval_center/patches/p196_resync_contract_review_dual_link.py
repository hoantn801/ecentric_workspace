# Copyright (c) 2026, eCentric and contributors
"""Contract Review: bay CA HAI duong mo tep - SharePoint va ban ERP (15/09, Hoan).

Ban truoc DOI lien ket sang SharePoint khi co, chu khong THEM. Do la loi nang hon phan quyen:
15/09 chi lien.vu - nguoi duyet cap 2 - bam "Mo online" va bi SharePoint chan. Luc do chi
khong phai "khong sua online duoc"; chi la KHONG DOC DUOC HOP DONG NUA, trong khi ban trong
ERP chi co day du quyen (da do: co DocShare tren ca EC-CTR-2026-00013 va 00014) van nam nguyen
do - chi la man hinh khong con tro toi no.

Luat rut ra, ghi lai vi no se con lap: mot tinh nang tien them KHONG duoc phep lam mat mot kha
nang von co. Them duong moi thi giu duong cu lam duong lui.

Landmark = dieu PHAI CO tren ban song sau khi sync."""
import frappe

from ecentric_workspace.approval_center.features.contract_review.infrastructure import page_sync

_LANDMARKS = ("Bản ERP", "sp_web_url")


def execute():
    res = page_sync.sync()
    action = (res or {}).get("action")
    frappe.log_error("p196 contract-review sync=%s" % action, "p196 resync")
    if action == "refused":
        frappe.log_error("p196: upsert TU CHOI GHI - trang KHONG duoc cap nhat.", "p196 REFUSED")
        return
    html = frappe.db.get_value("Web Page", {"route": "approvals/contract-review"},
                               "main_section_html") or ""
    thieu = [m for m in _LANDMARKS if m not in html]
    if thieu:
        frappe.log_error("p196: trang contract-review thieu dau moc %s" % thieu,
                         "p196 KHONG toi noi")
