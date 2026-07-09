# Copyright (c) 2026, eCentric and contributors
"""p034_create_purchase_request_page: create the Purchase Request Web Page at route
/approvals/purchase-request from source (run-once at migrate). Delegates to
purchase_request.page_sync.sync(). Published for UAT; catalog card stays inactive."""
import frappe

from ecentric_workspace.approval_center.purchase_request import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    res = page_sync.sync()
    frappe.logger("approval_center").info("p034_create_purchase_request_page: %s" % (res or {}))
