# Copyright (c) 2026, eCentric and contributors
"""Idempotent System Request Web Page sync. Delegates to the shared, ORM-only upsert
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

ROUTE = "approvals/system-request"
NAME = "system-request"               # Web Page is named after the route slug by Frappe
TITLE = "System Request"

# Unambiguous legacy-shim signatures (specific enough not to hit legitimate content).
_SHIM_MARKERS = ("SHIM cho Web Page", "frappe.db.get_doc", "frappe.db.get_value", "frappe.client")
# Text-like field types that could carry a script/HTML shim.
_TEXT_FIELDTYPES = {"Data", "Small Text", "Text", "Long Text", "Text Editor",
                    "Code", "HTML", "HTML Editor", "Markdown Editor"}
# Fields we own/replace with clean source (never blanked here).
_MANAGED_FIELDS = {"main_section", "main_section_html"}


def _html():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base, "frontend", "system_request.main_section.html"), encoding="utf-8") as fh:
        return fh.read()


def _strip_legacy_shims(name):
    """Meta-driven, ORM-only removal of a legacy shim from whatever text field actually holds it
    on this site. Never accesses a column that does not exist. main_section/main_section_html are
    left to the upsert (replaced with clean source). Returns diagnostic info."""
    inspected, stripped = [], []
    try:
        meta = frappe.get_meta("Web Page")
        doc = frappe.get_doc("Web Page", name)
    except Exception:
        return {"inspected_fields": inspected, "shim_fields_stripped": stripped, "has_legacy_shim": False}
    for df in meta.fields:
        if df.fieldtype not in _TEXT_FIELDTYPES or df.fieldname in _MANAGED_FIELDS:
            continue
        inspected.append(df.fieldname)
        val = doc.get(df.fieldname)
        if val and any(marker in val for marker in _SHIM_MARKERS):
            frappe.db.set_value("Web Page", name, df.fieldname, "")   # clear only the shim-bearing field
            stripped.append(df.fieldname)
    if stripped:
        frappe.db.commit()
        frappe.logger("approval_center").info(
            "system_request page_sync: stripped legacy shim from %s" % stripped)
    return {"inspected_fields": inspected, "shim_fields_stripped": stripped, "has_legacy_shim": bool(stripped)}


def sync(html=None):
    """Create-or-update the Web Page from clean source (idempotent), then strip any legacy shim
    found in a real Web Page field. Returns {action, route, name, inspected_fields,
    shim_fields_stripped, has_legacy_shim}."""
    html = html if html is not None else _html()
    res = page_sync_util.upsert_web_page(ROUTE, NAME, TITLE, html)   # main_section replaced with clean source
    if res.get("name") and frappe.db.exists("Web Page", res["name"]):
        res.update(_strip_legacy_shims(res["name"]))
    else:
        res.update({"inspected_fields": [], "shim_fields_stripped": [], "has_legacy_shim": False})
    return res


@frappe.whitelist(methods=["POST"])
def sync_system_request_page():
    """Admin-safe re-sync (System Manager only). Never publishes the catalog card."""
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the System Request page."), frappe.PermissionError)
    return sync()
