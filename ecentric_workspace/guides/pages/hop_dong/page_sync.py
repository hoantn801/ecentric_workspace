# Copyright (c) 2026, eCentric and contributors
"""Idempotent sync cho /huong-dan/hop-dong - bai huong dan hop dong (form 27 Contract Review).

Cung khuon voi guides/pages/dnmh_dntt: byte cua trang do REPO so huu hoan toan, moi lan sync
dung lai tu nguon. Khac: bai nay khong co anh chup ma co SO DO QUY TRINH THEO VAI TRO, viet
trong `quy_trinh.json` (dinh dang goi ISO) va ve bang bo ve cua Thu vien tai lieu ISO luc xem
- xem guides.flow_section. Sua quy trinh = sua quy_trinh.json + patch resync trang nay.

publish=1: nguoi dung noi bo nao cung doc duoc; trang khong chua du lieu phieu.
Khong mo endpoint sync rieng (bai khac co): patch goi sync(), bot mot cua whitelist.
"""
import os

import frappe

from ecentric_workspace.approval_center import page_sync_util as web_page
from ecentric_workspace.guides import page_sync_util as guides_util

ROUTE = "huong-dan/hop-dong"
NAME = "huong-dan-hop-dong"
TITLE = "Hướng dẫn: Hợp đồng (form 27)"

_HERE = os.path.dirname(os.path.abspath(__file__))

#: Xem chu thich cung ten o guides/pages/index/page_sync.py - ten tep phai xuat
#: hien nguyen van de ban ke ma bam nhin thay template nay.
TEMPLATE = "main_section.html"


def _html():
    return guides_util.build(_HERE, TEMPLATE)


def sync(html=None):
    html = html if html is not None else _html()
    res = web_page.upsert_web_page(ROUTE, NAME, TITLE, html, publish=1)
    if res.get("name") and frappe.db.exists("Web Page", res["name"]):
        res.update(web_page.strip_legacy_shims(res["name"]))
    return res

