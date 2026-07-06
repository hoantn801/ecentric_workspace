# Copyright (c) 2026, eCentric and contributors
"""Idempotent System Request Web Page sync. Delegates to the shared, ORM-only upsert
(approval_center.page_sync_util) so migrate re-runs / prior syncs never raise
DuplicateEntryError. Publishes the page for controlled/direct UAT; NEVER activates
the catalog card. No Approval Engine change."""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center import page_sync_util

ROUTE = "approvals/system-request"
NAME = "system-request"               # Web Page is named after the route slug by Frappe
TITLE = "System Request"


def _html():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base, "frontend", "system_request.main_section.html"), encoding="utf-8") as fh:
        return fh.read()


def sync(html=None):
    """Create-or-update the Web Page from source. Idempotent (safe to re-run / re-migrate).
    Returns {action: created|updated|unchanged, route, name}."""
    html = html if html is not None else _html()
    return page_sync_util.upsert_web_page(ROUTE, NAME, TITLE, html)


@frappe.whitelist(methods=["POST"])
def sync_system_request_page():
    """Admin-safe re-sync (System Manager only). Never publishes the catalog card."""
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the System Request page."), frappe.PermissionError)
    return sync()
