# Copyright (c) 2026, eCentric and contributors
"""Idempotent Resignation Web Page sync. Delegates to the shared, ORM-only upsert
(approval_center.page_sync_util) so migrate re-runs / prior syncs never raise
DuplicateEntryError, then removes any legacy Desk-style shim left on the live Web Page.

The shim (`// ===== SHIM cho Web Page ... frappe.db.get_doc ...`) POSTs to "/" on a
website page and pops a false "not found". It is NOT in our source and its location
varies by site, so we detect it dynamically via Web Page meta (never a hardcoded
column - this site's Web Page has no `head_html`). Publishes for UAT; never activates
the catalog card. No Approval Engine change."""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center import page_sync_util

ROUTE = "approvals/resignation"
NAME = "resignation"               # Web Page is named after the route slug by Frappe
TITLE = "Resignation"

def _html():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base, "frontend", "resignation.main_section.html"), encoding="utf-8") as fh:
        return fh.read()


def sync(html=None):
    """Create-or-update the Web Page from clean source (idempotent), then strip any legacy shim
    found in a real Web Page field. Returns {action, route, name, inspected_fields,
    shim_fields_stripped, has_legacy_shim}."""
    html = html if html is not None else _html()
    res = page_sync_util.upsert_web_page(ROUTE, NAME, TITLE, html)   # main_section replaced with clean source
    if res.get("name") and frappe.db.exists("Web Page", res["name"]):
        res.update(page_sync_util.strip_legacy_shims(res["name"]))
    else:
        res.update({"inspected_fields": [], "shim_fields_stripped": [], "has_legacy_shim": False})
    return res


@frappe.whitelist(methods=["POST"])
def sync_resignation_page():
    """Admin-safe re-sync (System Manager only). Never publishes the catalog card."""
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the Resignation page."), frappe.PermissionError)
    return sync()
