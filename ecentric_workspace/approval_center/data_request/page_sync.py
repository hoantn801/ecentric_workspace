# Copyright (c) 2026, eCentric and contributors
"""Versioned, idempotent Data Request Web Page sync. The page patch creates the
page once at migrate (run-once); Frappe will not re-run it, so frontend changes
need this whitelisted, admin-safe re-sync. Publishes the page for controlled/direct
UAT; NEVER activates the catalog card. No Approval Engine change."""
import os

import frappe
from frappe import _

ROUTE = "approvals/data-request"
NAME = "approval-center-data-request"
TITLE = "Data Request"


def _html():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base, "frontend", "data_request.main_section.html"), encoding="utf-8") as fh:
        return fh.read()


def sync(html=None):
    """Create-or-update the Web Page from source. Idempotent.
    Returns {action: created|updated|unchanged, route, name}."""
    if not frappe.db.exists("DocType", "Web Page"):
        return {"action": "skipped", "reason": "Web Page DocType missing", "route": ROUTE, "name": NAME}
    html = html if html is not None else _html()
    name = NAME if frappe.db.exists("Web Page", NAME) else None
    if not name:
        found = frappe.get_all("Web Page", filters={"route": ROUTE}, pluck="name")
        name = found[0] if found else None
    existed = bool(name)
    doc = frappe.get_doc("Web Page", name) if name else frappe.new_doc("Web Page")
    if existed and (doc.main_section or "") == html and (doc.main_section_html or "") == html \
            and doc.published and doc.title == TITLE:
        return {"action": "unchanged", "route": ROUTE, "name": doc.name}
    if not existed:
        doc.route = ROUTE
    doc.title = TITLE
    doc.published = 1
    doc.content_type = "HTML"
    doc.main_section = html
    doc.main_section_html = html
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    action = "updated" if existed else "created"
    frappe.logger("approval_center").info("data_request page_sync: %s Web Page /%s" % (action, ROUTE))
    return {"action": action, "route": ROUTE, "name": doc.name}


@frappe.whitelist(methods=["POST"])
def sync_data_request_page():
    """Admin-safe re-sync (System Manager only). Never publishes the catalog card."""
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the Data Request page."), frappe.PermissionError)
    return sync()
