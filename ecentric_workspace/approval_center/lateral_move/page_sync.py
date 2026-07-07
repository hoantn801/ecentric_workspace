# Copyright (c) 2026, eCentric and contributors
"""Idempotent Employee Lateral Move Web Page sync. Delegates to the shared ORM-only upsert
(no DuplicateEntryError) and strips any legacy Web Page shim via the shared
meta-driven helper. Publishes for UAT; never activates the catalog card."""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center import page_sync_util

ROUTE = "approvals/lateral-move"
NAME = "lateral-move"
TITLE = "Employee Lateral Move"


def _html():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base, "frontend", "lateral_move.main_section.html"), encoding="utf-8") as fh:
        return fh.read()


def sync(html=None):
    html = html if html is not None else _html()
    res = page_sync_util.upsert_web_page(ROUTE, NAME, TITLE, html)
    if res.get("name") and frappe.db.exists("Web Page", res["name"]):
        res.update(page_sync_util.strip_legacy_shims(res["name"]))
    return res


@frappe.whitelist(methods=["POST"])
def sync_lateral_move_page():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the Employee Lateral Move page."), frappe.PermissionError)
    return sync()
