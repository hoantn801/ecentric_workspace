# Copyright (c) 2026, eCentric and contributors
"""p009_create_data_request_page: create the Data Request Web Page at route
/approvals/data-request from source (run-once at migrate). Delegates to
data_request.page_sync.sync() so the migrate patch and the whitelisted admin
re-sync share ONE idempotent implementation. Published for UAT; catalog card
stays inactive."""
import frappe

from ecentric_workspace.approval_center.data_request import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    res = page_sync.sync()
    frappe.logger("approval_center").info("p009_create_data_request_page: %s" % (res or {}))
