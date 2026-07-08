# Copyright (c) 2026, eCentric and contributors
"""p030_create_leave_page: create the Leave Web Page at route /approvals/leave from source (run-once at
migrate). Delegates to leave.page_sync.sync(). Published for UAT; catalog card stays inactive."""
import frappe

from ecentric_workspace.approval_center.leave import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    res = page_sync.sync()
    frappe.logger("approval_center").info("p030_create_leave_page: %s" % (res or {}))
