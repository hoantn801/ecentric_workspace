# Copyright (c) 2026, eCentric and contributors
"""p026_create_special_bonus_page: create the Special Bonus Web Page at route
/approvals/special-bonus from source (run-once at migrate). Delegates to
special_bonus.page_sync.sync(). Published for UAT; catalog card stays inactive."""
import frappe

from ecentric_workspace.approval_center.special_bonus import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    res = page_sync.sync()
    frappe.logger("approval_center").info("p026_create_special_bonus_page: %s" % (res or {}))
