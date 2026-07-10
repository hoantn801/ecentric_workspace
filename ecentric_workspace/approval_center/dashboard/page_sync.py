# Copyright (c) 2026, eCentric and contributors
"""Idempotent Web Page sync for the Approval Center Operations Dashboard.
Route /approvals/dashboard. Delegates to the shared ORM-only upsert + legacy-shim strip.
Published for use; this is a reporting page (no catalog card involved)."""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center import page_sync_util

ROUTE = "approvals/dashboard"
NAME = "approvals-dashboard"
TITLE = "Approval Center Dashboard"


def _html():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base, "frontend", "approvals_dashboard.main_section.html"), encoding="utf-8") as fh:
        return fh.read()


def sync(html=None):
    html = html if html is not None else _html()
    res = page_sync_util.upsert_web_page(ROUTE, NAME, TITLE, html)
    if res.get("name") and frappe.db.exists("Web Page", res["name"]):
        res.update(page_sync_util.strip_legacy_shims(res["name"]))
    return res


@frappe.whitelist(methods=["POST"])
def sync_dashboard_page():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the Approval Center Dashboard page."), frappe.PermissionError)
    return sync()
