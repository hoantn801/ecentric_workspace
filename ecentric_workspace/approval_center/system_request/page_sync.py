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


# Desk-style client APIs a legacy head_html shim may contain. Our main_section is fully
# self-contained (own shell markup + styles) and needs no head_html, so if the live Web Page
# still carries such a shim we strip it (it POSTs to "/" on a website page and pops a false
# "not found"). Surgical: only clears head_html when it actually contains one of these.
_HEAD_SHIM_MARKERS = ("frappe.db.get_doc", "frappe.db.get_value", "frappe.client")


def _strip_head_shim(name):
    """Remove a legacy Desk-style shim from the Web Page head_html (ORM-only, non-destructive
    to legitimate head_html). Returns True if it stripped one."""
    head = frappe.db.get_value("Web Page", name, "head_html") or ""
    if any(m in head for m in _HEAD_SHIM_MARKERS):
        frappe.db.set_value("Web Page", name, "head_html", "")
        frappe.db.commit()
        frappe.logger("approval_center").info("system_request page_sync: stripped legacy head_html shim")
        return True
    return False


def sync(html=None):
    """Create-or-update the Web Page from source. Idempotent (safe to re-run / re-migrate).
    Also strips any legacy Desk-style head_html shim. Returns {action, route, name, head_stripped}."""
    html = html if html is not None else _html()
    res = page_sync_util.upsert_web_page(ROUTE, NAME, TITLE, html)
    if res.get("name") and frappe.db.exists("Web Page", res["name"]):
        res["head_stripped"] = _strip_head_shim(res["name"])
    return res


@frappe.whitelist(methods=["POST"])
def sync_system_request_page():
    """Admin-safe re-sync (System Manager only). Never publishes the catalog card."""
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the System Request page."), frappe.PermissionError)
    return sync()
