# Copyright (c) 2026, eCentric and contributors
"""p022_create_resignation_page: create the Resignation Request Web Page at route
/approvals/resignation from source (run-once at migrate). Delegates to
resignation.page_sync.sync(). Published for UAT; catalog card stays inactive."""
import frappe

from ecentric_workspace.approval_center.resignation import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    res = page_sync.sync()
    frappe.logger("approval_center").info("p022_create_resignation_page: %s" % (res or {}))
