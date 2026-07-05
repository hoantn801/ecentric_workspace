# Copyright (c) 2026, eCentric and contributors
"""p008_create_outside_work_page: create the Outside Work Web Page at route
/approvals/outside-work from source (run-once at migrate). Delegates to
outside_work.page_sync.sync() so the migrate patch and the whitelisted admin
re-sync share ONE idempotent implementation. Published for UAT; catalog card
stays inactive. Does NOT touch /approval or the AI Topup page."""
import frappe

from ecentric_workspace.approval_center.outside_work import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    res = page_sync.sync()
    frappe.logger("approval_center").info("p008_create_outside_work_page: %s" % (res or {}))
