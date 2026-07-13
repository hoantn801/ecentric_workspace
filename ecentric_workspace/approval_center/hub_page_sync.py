# Copyright (c) 2026, eCentric and contributors
"""Idempotent sync for the Approval Center hub Web Page (/approvals).

The hub was historically shipped by data patches p003-p005; Phase 1B gives it
the same SM-gated, migrate-free sync path every /approvals/<type> page already
has (mirrors leave/page_sync.py; shared ORM-only upsert)."""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center import page_sync_util

ROUTE = "approvals"
NAME = "approval-center"
TITLE = "Approval Center"


def _html():
    base = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(base, "frontend", "approvals.main_section.html"), encoding="utf-8") as fh:
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
def sync_approvals_page():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the Approval Center page."), frappe.PermissionError)
    return sync()
