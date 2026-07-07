# Copyright (c) 2026, eCentric and contributors
"""p023_create_promotion_page: create the Promotion Request Web Page at route
/approvals/promotion from source (run-once at migrate). Delegates to
promotion.page_sync.sync(). Published for UAT; catalog card stays inactive."""
import frappe

from ecentric_workspace.approval_center.promotion import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    res = page_sync.sync()
    frappe.logger("approval_center").info("p023_create_promotion_page: %s" % (res or {}))
