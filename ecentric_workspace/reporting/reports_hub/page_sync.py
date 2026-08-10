# Copyright (c) 2026, eCentric and contributors
"""Idempotent sync for the Reports Center hub Web Page. Route /reports
(Web Page "reports-center"). HTML is repo-owned; created on migrate by patch."""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center import page_sync_util

ROUTE = "reports"
NAME = "reports-center"
TITLE = "Trung tâm Báo cáo"


def _html():
    base = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(base, "..", "frontend", "reports.main_section.html"),
              encoding="utf-8") as fh:
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
def sync_reports_page():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the /reports page."), frappe.PermissionError)
    return sync()
