# Copyright (c) 2026, eCentric and contributors
"""Popup hub: the phai cao BANG the trai, va nut "Gui" can giua lai (09/09, Hoan chot).

Hai thu Hoan chi tren anh chup sau khi tab Trao doi chay duoc:
  1. `.ec-apl-wrap` dung `align-items:flex-start` nen the phai chi cao bang noi dung cua no -
     ho so nhieu cap thi the trai dai gap doi, nhin lech han. Doi sang `stretch`, va bien
     `.ec-apl-aside` thanh cot flex de phan than (`.bd`) an het cho thua con o nhap tin nhan
     luon dinh day, thay vi de mot khoang trang lo lung o giua.
     KHONG dung `align-items:center` - no cat mat phan dau khi the cao hon man hinh (ly do
     da ghi san trong chinh file do tu truoc).
  2. Nut "Gui": chu co dau bi day lech khi de line-height mac dinh. Can giua tuong minh
     bang inline-flex + line-height:1.

Kem mot don dep: nut gui truoc do mang class "approve" - vo nghia, vi rule `.btn.approve`
bi gioi han trong `.ec-apl-mf` nen khong voi toi khung chat. Bo di de nguoi doc sau khong
tuong nut nay dang mang mau cua nut Duyet. Hai nut Duyet that o `.ec-apl-mf` giu nguyen.

KHONG BAO GIO nem loi ngoai gate: patch chay trong migrate (bai hoc p116). Landmark duoi day
chi de xac nhan HTML da len that; thieu thi bao de nguoi deploy biet, khong am tham bo qua.
"""
import frappe

from ecentric_workspace.approval_center.ui.all_requests import page_sync

_LANDMARKS = ("align-items:stretch", "min-width:68px", "flex-direction:column")


def execute():
    res = page_sync.sync()
    frappe.log_error("p171 all_requests sync=%s" % (res or {}).get("action"), "p171 resync")
    html = frappe.db.get_value("Web Page", {"route": "approvals/all-requests"},
                               "main_section_html") or ""
    missing = [m for m in _LANDMARKS if m not in html]
    if missing:
        raise Exception("p171: trang all-requests thieu dau moc %s" % missing)
