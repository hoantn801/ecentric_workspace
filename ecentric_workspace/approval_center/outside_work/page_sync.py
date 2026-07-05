# Copyright (c) 2026, eCentric and contributors
"""Versioned, idempotent Outside Work Web Page sync. p008 creates the page once at
migrate (run-once); Frappe will not re-run it, so frontend changes need this
whitelisted, admin-safe re-sync that create/updates the page from the current
source HTML. Publishes the page for controlled/direct UAT; NEVER activates the
catalog card. No Approval Engine / AI Topup change."""
import os

import frappe
from frappe import _

ROUTE = "approvals/outside-work"
NAME = "approval-center-outside-work"
TITLE = "Outside Work"


def _html():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base, "frontend", "outside_work.main_section.html"), encoding="utf-8") as fh:
        return fh.read()


def sync(html=None):
    """Create-or-update the Web Page from source. Idempotent; safe if p008 already
    created it. Returns {action: created|updated|unchanged, route, name}."""
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
    doc.published = 1                # controlled/direct UAT; catalog card stays inactive
    doc.content_type = "HTML"
    doc.main_section = html
    doc.main_section_html = html
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    action = "updated" if existed else "created"
    frappe.logger("approval_center").info("outside_work page_sync: %s Web Page /%s" % (action, ROUTE))
    return {"action": action, "route": ROUTE, "name": doc.name}


@frappe.whitelist(methods=["POST"])
def sync_outside_work_page():
    """Admin-safe re-sync (System Manager only). Re-runs after a frontend change
    without editing the Web Page by hand. Never publishes the catalog card."""
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the Outside Work page."), frappe.PermissionError)
    return sync()
