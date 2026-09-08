# Copyright (c) 2026, eCentric and contributors
"""Idempotent sync cho /huong-dan/dnmh-dntt — bài hướng dẫn DNMH → DNTT.

Byte cua trang do REPO so huu hoan toan (khong co du lieu nghiep vu), nen khong dung
khoa chong troi: moi lan sync la dung lai tu nguon. Anh chup man hinh nam trong
`img/` va duoc nhung base64 luc sync (xem guides.page_sync_util).

publish=1: nguoi dung noi bo nao cung doc duoc; trang khong chua du lieu phieu, chi
la anh chup form trong + mot phieu mau da hoan tat (dong y boi Hoan 08/09).
"""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center import page_sync_util as web_page
from ecentric_workspace.guides import page_sync_util as guides_util

ROUTE = "huong-dan/dnmh-dntt"
NAME = "huong-dan-dnmh-dntt"
TITLE = "Hướng dẫn: Đề nghị mua hàng → Đề nghị thanh toán"

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


@frappe.whitelist(methods=["POST"])
def sync_guide_dnmh_dntt():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Chỉ System Manager mới được đồng bộ trang hướng dẫn."),
                     frappe.PermissionError)
    return sync()
