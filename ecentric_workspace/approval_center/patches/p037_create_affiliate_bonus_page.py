# Copyright (c) 2026, eCentric and contributors
"""p037_create_affiliate_bonus_page: create the Affiliate Bonus Web Page at route
/approvals/affiliate-bonus-request from source (run-once at migrate). Delegates to
affiliate_bonus.page_sync.sync(). Published for UAT; catalog card stays inactive."""
import frappe

from ecentric_workspace.approval_center.affiliate_bonus import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    res = page_sync.sync()
    frappe.logger("approval_center").info("p037_create_affiliate_bonus_page: %s" % (res or {}))
