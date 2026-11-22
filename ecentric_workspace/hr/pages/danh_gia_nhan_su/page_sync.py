# Copyright (c) 2026, eCentric and contributors
"""Idempotent sync cho /ec-hr/danh-gia-nhan-su - hang cho Danh gia nhan su cua C&B (23/11/2026).

Trang moi, repo so huu toan bo byte, khong co lich su song can giu -> upsert thang (giong
hr/pages/tong_quan). Dung sua trong Desk: sua main_section.html roi chay lai sync (patch resync +
resync_manifest.json). Quyen: trang publish cho nguoi dang nhap; DU LIEU do API hang_cho tra,
API chan nguoi khong co role EC CnB / HR."""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center import page_sync_util

ROUTE = "ec-hr/danh-gia-nhan-su"
NAME = "danh-gia-nhan-su"
TITLE = "Hàng chờ đánh giá nhân sự"


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
def sync_danh_gia_nhan_su_page():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the /ec-hr/danh-gia-nhan-su page."),
                     frappe.PermissionError)
    return sync()
