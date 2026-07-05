# Copyright (c) 2026, eCentric and contributors
"""p012_create_system_request_page: create the System Request Web Page at route
/approvals/system-request from source (run-once at migrate). Delegates to
system_request.page_sync.sync(). Published for UAT; catalog card stays inactive."""
import frappe

from ecentric_workspace.approval_center.system_request import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    res = page_sync.sync()
    frappe.logger("approval_center").info("p012_create_system_request_page: %s" % (res or {}))
