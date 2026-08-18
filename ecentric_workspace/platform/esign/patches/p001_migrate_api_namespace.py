# Copyright (c) 2026, eCentric and contributors
"""Migrate persisted Web Page calls to the canonical platform e-sign API."""

import frappe


LEGACY_API = "ecentric_workspace.approval_center.esign.api."
PLATFORM_API = "ecentric_workspace.platform.esign.api."


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return

    pages = frappe.get_all(
        "Web Page",
        filters={"main_section_html": ["like", f"%{LEGACY_API}%"]},
        pluck="name",
    )
    for name in pages:
        html = frappe.db.get_value("Web Page", name, "main_section_html") or ""
        migrated = html.replace(LEGACY_API, PLATFORM_API)
        if migrated != html:
            frappe.db.set_value(
                "Web Page", name, "main_section_html", migrated, update_modified=False
            )
