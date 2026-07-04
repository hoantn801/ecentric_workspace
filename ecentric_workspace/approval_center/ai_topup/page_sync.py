# Copyright (c) 2026, eCentric and contributors
"""Versioned, idempotent AI Topup Web Page sync. Replaces reliance on the
run-once p006: a whitelisted admin-safe function + a versioned patch (p007) that
create/update the page from the current source HTML. Publishes the page for
controlled/direct UAT; NEVER activates the catalog card."""
import os

import frappe
from frappe import _

ROUTE = "approvals/ai-topup"
NAME = "approval-center-ai-topup"
TITLE = "AI Topup"


def _html():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base, "frontend", "ai_topup.main_section.html"), encoding="utf-8") as fh:
        return fh.read()


def sync(html=None):
    """Create-or-update the Web Page. Idempotent; safe if p006 already created it.
    Returns {action: created|updated, route, name}."""
    if not frappe.db.exists("DocType", "Web Page"):
        return {"action": "skipped", "reason": "Web Page DocType missing"}
    html = html if html is not None else _html()
    name = NAME if frappe.db.exists("Web Page", NAME) else None
    if not name:
        found = frappe.get_all("Web Page", filters={"route": ROUTE}, pluck="name")
        name = found[0] if found else None
    existed = bool(name)
    doc = frappe.get_doc("Web Page", name) if name else frappe.new_doc("Web Page")
    if not existed:
        doc.route = ROUTE
    doc.title = TITLE
    doc.published = 1                # controlled/direct UAT; card stays inactive
    doc.content_type = "HTML"
    doc.main_section = html
    doc.main_section_html = html
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    action = "updated" if existed else "created"
    frappe.logger("approval_center").info("page_sync: %s Web Page /%s" % (action, ROUTE))
    return {"action": action, "route": ROUTE, "name": doc.name}


@frappe.whitelist(methods=["POST"])
def sync_ai_topup_page():
    """Admin-safe re-sync (System Manager only). No manual Web Page edits needed."""
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the AI Topup page."), frappe.PermissionError)
    return sync()
