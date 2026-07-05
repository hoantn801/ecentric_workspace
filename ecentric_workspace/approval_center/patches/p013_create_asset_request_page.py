# Copyright (c) 2026, eCentric and contributors
"""p013_create_asset_request_page: create the Asset Request Web Page at route
/approvals/asset-request from source (run-once at migrate). Delegates to
asset_request.page_sync.sync(). Published for UAT; catalog card stays inactive."""
import frappe

from ecentric_workspace.approval_center.asset_request import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    res = page_sync.sync()
    frappe.logger("approval_center").info("p013_create_asset_request_page: %s" % (res or {}))
