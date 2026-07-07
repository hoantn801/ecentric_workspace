# Copyright (c) 2026, eCentric and contributors
"""p028_create_hiring_request_page: create the Hiring Request Web Page at route
/approvals/hiring-request from source (run-once at migrate). Delegates to
hiring_request.page_sync.sync(). Published for UAT; catalog card stays inactive."""
import frappe

from ecentric_workspace.approval_center.hiring_request import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    res = page_sync.sync()
    frappe.logger("approval_center").info("p028_create_hiring_request_page: %s" % (res or {}))
