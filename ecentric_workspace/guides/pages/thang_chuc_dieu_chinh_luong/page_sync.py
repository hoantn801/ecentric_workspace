# Copyright (c) 2026, eCentric and contributors
"""Idempotent sync cho /huong-dan/thang-chuc-dieu-chinh-luong — thang chuc dieu chinh luong.

Bai huong dan quy trinh nhan su (24/11/2026, bo huong dan nhan su day du). Byte cua trang do REPO
so huu hoan toan (khong co du lieu nghiep vu) nen khong dung khoa chong troi: moi lan sync
la dung lai tu nguon. So do luong la ma mermaid trong trang, ve tai trinh duyet bang asset
cuc bo (public/vendor/mermaid + public/guides/ec_guide_flow.js) - khong goi CDN.

publish=1: nguoi dung noi bo nao cung doc duoc; trang khong chua du lieu phieu.
"""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center import page_sync_util as web_page
from ecentric_workspace.guides import page_sync_util as guides_util

ROUTE = "huong-dan/thang-chuc-dieu-chinh-luong"
NAME = "huong-dan-thang-chuc-dieu-chinh-luong"
TITLE = "Hướng dẫn: Thăng chức / điều chỉnh lương"

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
def sync_guide_thang_chuc_dieu_chinh_luong():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Chỉ System Manager mới được đồng bộ trang hướng dẫn."),
                     frappe.PermissionError)
    return sync()
