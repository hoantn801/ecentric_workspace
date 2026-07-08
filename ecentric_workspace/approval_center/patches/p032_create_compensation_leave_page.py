# Copyright (c) 2026, eCentric and contributors
"""p032_create_compensation_leave_page: create the Compensation Leave Web Page at route /approvals/compensation-leave from source (run-once at
migrate). Delegates to compensation_leave.page_sync.sync(). Published for UAT; catalog card stays inactive."""
import frappe

from ecentric_workspace.approval_center.compensation_leave import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    res = page_sync.sync()
    frappe.logger("approval_center").info("p032_create_compensation_leave_page: %s" % (res or {}))
