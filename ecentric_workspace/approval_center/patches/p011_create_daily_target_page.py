# Copyright (c) 2026, eCentric and contributors
"""p011_create_daily_target_page: create the Daily Target Web Page at route
/approvals/daily-target from source (run-once at migrate). Delegates to
daily_target.page_sync.sync(). Published for UAT; catalog card stays inactive."""
import frappe

from ecentric_workspace.approval_center.daily_target import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    res = page_sync.sync()
    frappe.logger("approval_center").info("p011_create_daily_target_page: %s" % (res or {}))
