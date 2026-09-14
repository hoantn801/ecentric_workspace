# Copyright (c) 2026, eCentric and contributors
"""Hub: dinh kem tro sang ban tren SharePoint de mo bang Word Online (14/09, Hoan).

Truoc dot nay the dinh kem tro thang vao `file_url` cua Frappe. Trinh duyet gap mot .docx o
duong dan do thi luon TAI VE - do la rang buoc cua Office (Word Online chi mo duoc tep nam
tren SharePoint/OneDrive), khong phai thieu cau hinh. Nguoi duyet muon doc/comment online thi
phai tai ve, sua, roi dinh kem lai - va ban tren ERP lap tuc phan nhanh.

Sau dot nay: khi phieu da co ban tren SharePoint, `query_service` gan them `sp_web_url` vao
tung dinh kem va the tro sang do, kem nhan "online".

Kem theo la bang canh bao "tep doi sau khi da co cap duyet". CANH BAO, KHONG CHAN: ban tren
SharePoint la ban SONG (Hoan chot cho sua/comment truc tiep) nen tep doi la chuyen binh
thuong - nguoi duyet sua mot cau chu cung lam moc thoi gian nhay. Dieu can noi ro la CAP NAO
da duyet TRUOC luc tep doi lan cuoi, tuc ho duyet tren mot ban khong con y nguyen.

Landmark = dieu PHAI CO tren ban song sau khi sync."""
import frappe

from ecentric_workspace.approval_center.ui.all_requests import page_sync

_LANDMARKS = ("sp_web_url", "ec-apl-stale")


def execute():
    res = page_sync.sync()
    action = (res or {}).get("action")
    frappe.log_error("p187 all-requests sync=%s" % action, "p187 resync")
    if action == "refused":
        frappe.log_error("p187: upsert TU CHOI GHI - trang KHONG duoc cap nhat.", "p187 REFUSED")
        return
    html = frappe.db.get_value("Web Page", {"route": "approvals/all-requests"},
                               "main_section_html") or ""
    thieu = [m for m in _LANDMARKS if m not in html]
    if thieu:
        frappe.log_error("p187: trang all-requests thieu dau moc %s" % thieu,
                         "p187 KHONG toi noi")
