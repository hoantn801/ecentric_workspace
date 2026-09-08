# Copyright (c) 2026, eCentric and contributors
"""Idempotent sync cho /huong-dan — MUC LUC cac bai huong dan su dung.

Danh sach bai sinh tu `guides.registry` luc sync, nen them mot bai moi = them mot
muc trong registry + mot thu muc trang; KHONG phai sua trang muc luc bang tay.

Vi sao muc luc nam o menu ma tung bai thi khong: menu ben trai la thu nguoi dung
nhin thay MOI ngay - nhoi 24 bai vao do thi no dai vo tan va lan nao them form
cung phai sua menu. Loi vao dung luc can la icon "?" tren the / tren chinh form
(tro thang toi bai cua form do); menu chi can mot cua vao duy nhat.
"""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center import page_sync_util as web_page
from ecentric_workspace.guides import page_sync_util as guides_util

ROUTE = "huong-dan"
NAME = "huong-dan"
TITLE = "Hướng dẫn sử dụng"

_HERE = os.path.dirname(os.path.abspath(__file__))


#: Ghi thang ten tep (thay vi de guides_util.build tu mac dinh): bo kiem
#: test_html_change_needs_resync doc AST cua CHINH module nay de tim template
#: duoc bom vao trang. Khong co chuoi ".html" o day thi trang huong dan lang le
#: nam ngoai ban ke ma bam - sua HTML ma khong ai bat buoc phai co patch resync.
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
def sync_guides_index():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Chỉ System Manager mới được đồng bộ trang hướng dẫn."),
                     frappe.PermissionError)
    return sync()
