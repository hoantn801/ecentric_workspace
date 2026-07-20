# Copyright (c) 2026, eCentric and contributors
"""Idempotent sync for the LEGACY /client-request Web Page (document page).

Repo-ization: main_section.html imported VERBATIM via a UTF-8-safe extraction
(main_section == main_section_html, sha-verified; 0 mojibake), NOT the PS5
snapshot pipeline. First sync against unchanged live content returns
{"action": "unchanged"}. All business/GBS/chain logic lives in the page body and
is governed by live Server Scripts; this module only ships HTML."""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center import page_sync_util

ROUTE = "client-request"
NAME = "client-code-request"
TITLE = "Client Code Request"


def _html():
    base = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(base, "main_section.html"), encoding="utf-8") as fh:
        return fh.read()


def sync(html=None):
    html = html if html is not None else _html()
    res = page_sync_util.upsert_web_page(ROUTE, NAME, TITLE, html)
    if res.get("name") and frappe.db.exists("Web Page", res["name"]):
        res.update(page_sync_util.strip_legacy_shims(res["name"]))
        from ecentric_workspace.legacy_pages import serving
        res.update(serving.ensure_static_serving(res["name"], html))
    return res


@frappe.whitelist(methods=["POST"])
def sync_client_request_page():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the /client-request page."), frappe.PermissionError)
    return sync()
