# Copyright (c) 2026, eCentric and contributors
"""p031_create_late_early_out_page: create the Late in - Early out Web Page at route /approvals/late-in-early-out from source (run-once at
migrate). Delegates to late_early_out.page_sync.sync(). Published for UAT; catalog card stays inactive."""
import frappe

from ecentric_workspace.approval_center.late_early_out import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    res = page_sync.sync()
    frappe.logger("approval_center").info("p031_create_late_early_out_page: %s" % (res or {}))
