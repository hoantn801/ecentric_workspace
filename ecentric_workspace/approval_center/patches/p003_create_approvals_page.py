# Copyright (c) 2026, eCentric and contributors
"""p003_create_approvals_page: create/refresh the Approval Center Web Page at
route `/approvals` from the source template. Code-owned page (Git is the source
of truth), so migrate re-applies the current HTML. Idempotent.

Does NOT touch the existing `/approval` inbox. No schema change.
Rollback: non-destructive — un-publish or delete the `approval-center` Web Page.
"""
import os

import frappe

ROUTE = "approvals"
NAME = "approval-center"
TITLE = "Approval Center"


def _html():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base, "frontend", "approvals.main_section.html"), encoding="utf-8") as fh:
        return fh.read()


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    html = _html()

    name = None
    if frappe.db.exists("Web Page", NAME):
        name = NAME
    else:
        found = frappe.get_all("Web Page", filters={"route": ROUTE},
                               fields=["name"], limit_page_length=1)
        if found:
            name = found[0].name

    if name:
        doc = frappe.get_doc("Web Page", name)
    else:
        doc = frappe.new_doc("Web Page")
        doc.route = ROUTE

    doc.title = TITLE
    doc.published = 1
    doc.content_type = "HTML"
    doc.main_section = html
    doc.main_section_html = html
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    frappe.logger("approval_center").info("p003_create_approvals_page: upserted /%s" % ROUTE)
