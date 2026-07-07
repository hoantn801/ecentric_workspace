# Copyright (c) 2026, eCentric and contributors
"""p024_create_lateral_move_page: create the Employee Lateral Move Web Page at route
/approvals/lateral-move from source (run-once at migrate). Delegates to
lateral_move.page_sync.sync(). Published for UAT; catalog card stays inactive."""
import frappe

from ecentric_workspace.approval_center.lateral_move import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    res = page_sync.sync()
    frappe.logger("approval_center").info("p024_create_lateral_move_page: %s" % (res or {}))
