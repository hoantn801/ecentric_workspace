# Copyright (c) 2026, eCentric and contributors
"""Idempotent sync cho /huong-dan/chot-cong-thang - bai huong dan chot cong thang +
phan bo cong viec (brand weight).

Cung khuon voi guides/pages/dnmh_dntt: byte cua trang do REPO so huu hoan toan, moi
lan sync dung lai tu nguon; anh chup man hinh nam trong `img/`, nhung base64 luc sync.

publish=1: nguoi dung noi bo nao cung doc duoc. Anh chup la trang Cham cong / Phan bo
cong viec cua tai khoan Hoan va ten nhan vien trong team (khong co so lieu luong) -
Hoan gui anh va duyet dua len 01/10/2026.
"""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center import page_sync_util as web_page
from ecentric_workspace.guides import page_sync_util as guides_util

ROUTE = "huong-dan/chot-cong-thang"
NAME = "huong-dan-chot-cong-thang"
TITLE = "Hướng dẫn: Chốt công tháng & Phân bổ công việc"

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
def sync_guide_chot_cong_thang():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Chỉ System Manager mới được đồng bộ trang hướng dẫn."),
                     frappe.PermissionError)
    return sync()
