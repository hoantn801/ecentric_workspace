# Copyright (c) 2026, eCentric and contributors
"""p035_create_payment_request_page: create the Payment Request Web Page at route
/approvals/payment-request from source (run-once at migrate). Delegates to
payment_request.page_sync.sync(). Published for UAT; catalog card stays inactive."""
import frappe

from ecentric_workspace.approval_center.payment_request import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    res = page_sync.sync()
    frappe.logger("approval_center").info("p035_create_payment_request_page: %s" % (res or {}))
