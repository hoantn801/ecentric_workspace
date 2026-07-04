# Copyright (c) 2026, eCentric and contributors
"""p006_create_ai_topup_page: create/refresh the AI Topup Web Page at route
/approvals/ai-topup from source. Code-owned page; idempotent. Published so the
direct route works for System Manager/test users during UAT - but the catalog
card stays INACTIVE and AI_TOPUP-V1 stays Draft, so submit is naturally gated
(no Active process) until explicit activation. Does NOT touch /approval."""
import os

import frappe

ROUTE = "approvals/ai-topup"
NAME = "approval-center-ai-topup"
TITLE = "AI Topup"


def _html():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base, "frontend", "ai_topup.main_section.html"), encoding="utf-8") as fh:
        return fh.read()


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    html = _html()
    name = NAME if frappe.db.exists("Web Page", NAME) else None
    if not name:
        found = frappe.get_all("Web Page", filters={"route": ROUTE}, fields=["name"], limit_page_length=1)
        name = found[0].name if found else None
    doc = frappe.get_doc("Web Page", name) if name else frappe.new_doc("Web Page")
    if not name:
        doc.route = ROUTE
    doc.title = TITLE
    doc.published = 1
    doc.content_type = "HTML"
    doc.main_section = html
    doc.main_section_html = html
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    frappe.logger("approval_center").info("p006_create_ai_topup_page: upserted /%s" % ROUTE)
