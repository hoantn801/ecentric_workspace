# Copyright (c) 2026, eCentric and contributors
"""Idempotent Compensation Leave Web Page sync via the shared ORM-only upsert + meta-driven shim strip.
Publishes for UAT; never activates the catalog card."""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center import page_sync_util

ROUTE = "approvals/compensation-leave"
NAME = "compensation-leave"
TITLE = "Compensation Leave"


def _html():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base, "frontend", "compensation_leave.main_section.html"), encoding="utf-8") as fh:
        return fh.read()


def sync(html=None):
    html = html if html is not None else _html()
    res = page_sync_util.upsert_web_page(ROUTE, NAME, TITLE, html)
    if res.get("name") and frappe.db.exists("Web Page", res["name"]):
        res.update(page_sync_util.strip_legacy_shims(res["name"]))
    else:
        res.update({"inspected_fields": [], "shim_fields_stripped": [], "has_legacy_shim": False})
    return res


@frappe.whitelist(methods=["POST"])
def sync_compensation_leave_page():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the Compensation Leave page."), frappe.PermissionError)
    return sync()
