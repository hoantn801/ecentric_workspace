# Copyright (c) 2026, eCentric and contributors
"""Idempotent sync cho /ai-live -- SI Tool > Quan ly AI Live (25/10/2026, tach khoi /ai-video).

BYTES OWNED BY THE REPO (giong ai_tools/pages/ai_video): trang moi, upsert thang. Dung sua
trong Desk -- sua main_section.html roi chay lai sync (patch resync + resync_manifest.json).
Du lieu: ecentric_workspace.ai_tools.features.ai_live.controllers.api.* (server tu kiem quyen).
"""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center import page_sync_util

ROUTE = "ai-live"
NAME = "ai-live"
TITLE = "Quản lý AI Live"


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
def sync_ai_live_page():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the /ai-live page."), frappe.PermissionError)
    return sync()
