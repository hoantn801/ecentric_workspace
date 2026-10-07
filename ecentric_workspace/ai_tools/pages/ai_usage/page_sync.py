# Copyright (c) 2026, eCentric and contributors
"""Idempotent sync cho /ai-usage -- Thong ke dung AI cua nhan su (07/10/2026).

BYTES OWNED BY THE REPO (giong ai_tools/pages/ai_video): trang moi, upsert thang. Dung sua
trong Desk -- sua main_section.html roi chay lai sync (patch resync + resync_manifest.json).
Du lieu: ecentric_workspace.platform.ai.usage_api.summary (server tu kep pham vi xem).
"""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center import page_sync_util

ROUTE = "ai-usage"
NAME = "ai-usage"
TITLE = "Thống kê dùng AI"


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
def sync_ai_usage_page():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the /ai-usage page."), frappe.PermissionError)
    return sync()
