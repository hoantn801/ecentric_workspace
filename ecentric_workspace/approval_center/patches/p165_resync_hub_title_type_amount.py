# Copyright (c) 2026, eCentric and contributors
"""Bang "Tat ca yeu cau": tieu de that, loai doc duoc, them cot Chi phi (09/09, Hoan).

Truoc do bang khong he lay tieu de phieu: cot "Tieu de" hien approval_title cua LOAI phieu
("Payment Request") con cot "Loai" hien MA loai ("PAYMENT_REQUEST"). Ca trang 15 dong giong
het nhau nen khong phan biet duoc phieu nao voi phieu nao.

  * Tieu de  <- request_title cua phieu (khong co thi lui ve ten loai).
  * Loai     <- nhan nguoi doc duoc, khong con MA gach duoi.
  * Chi phi  <- cot moi. So DE NGHI BAN DAU (chot voi Hoan), khong phai so thuc te sau duyet,
                de mot phieu nhin trong danh sach khong doi so theo thoi gian. Hien ma tien te
                khi khac VND. Form khong co truong tien thi de TRONG - trong va 0 khac nhau.

Tieu de va so tien nam o DocType nghiep vu chu khong o EC Approval Request, nen doc THEO LO
(reporting/business_summary.py): mot truy van cho moi DocType tren trang, khong phai moi dong
mot truy van. Chi de hien thi, khong noi rong quyen - chi doc nhung phieu da nam trong pham vi
ma truy van hub tra ve.

Trang hub KHONG co khoa chong troi (upsert khong truyen expect_sha) nen khong can bump sha.
Patch moi vi cac patch resync truoc da chay tren production. Tu VERIFY landmark.
"""
import frappe

from ecentric_workspace.approval_center.ui.all_requests import page_sync

_LANDMARKS = ("cell(r.title||r.type)", "function fmtMoney(", "Chi phí")


def execute():
    res = page_sync.sync()
    frappe.log_error("p165 all_requests sync=%s" % (res or {}).get("action"), "p165 resync")
    html = frappe.db.get_value("Web Page", {"route": "approvals/all-requests"},
                               "main_section_html") or ""
    missing = [m for m in _LANDMARKS if m not in html]
    if missing:
        raise Exception("p165: hub thieu %s sau sync (action=%s)"
                        % (missing, (res or {}).get("action")))
