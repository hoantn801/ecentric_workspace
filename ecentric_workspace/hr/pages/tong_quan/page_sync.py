# Copyright (c) 2026, eCentric and contributors
"""Idempotent sync cho /tong-quan -- trang Tong quan cua portal (truoc la /coming-soon).

MOT HUB, NHIEU THE
  /tong-quan la luoi the theo mang (the dau tien: Nhan su). Bam the -> #nhan-su voi 3 tab
  Bang dieu khien / Danh sach / So do phong ban. Them phong ban khac sau nay = them the
  (hr.overview.api.get_cards + mot nhanh render), khong can trang moi.

KHONG CO LOGIC / KHONG CO LUONG TRONG TRANG
  Moi so lieu do ecentric_workspace.hr.overview.api tra ve; truong nao duoc tra do
  permlevel cua Employee quyet dinh. Trang khong hien so luong nao.

BYTES OWNED BY THE REPO
  Giong action_center/pages/my_work: trang moi, khong co lich su song can giu, nen upsert
  thang, khong khoa drift. Dung sua trong Desk -- sua main_section.html roi chay lai sync
  (patch resync + resync_manifest.json).
"""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center import page_sync_util

ROUTE = "tong-quan"
NAME = "tong-quan"
TITLE = "Tổng quan"


def _html():
    base = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(base, "main_section.html"), encoding="utf-8") as fh:
        return fh.read()


def sync(html=None):
    html = html if html is not None else _html()
    res = page_sync_util.upsert_web_page(ROUTE, NAME, TITLE, html, publish=1)
    if res.get("name") and frappe.db.exists("Web Page", res["name"]):
        res.update(page_sync_util.strip_legacy_shims(res["name"]))
    return res


@frappe.whitelist(methods=["POST"])
def sync_tong_quan_page():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the /tong-quan page."),
                     frappe.PermissionError)
    return sync()
