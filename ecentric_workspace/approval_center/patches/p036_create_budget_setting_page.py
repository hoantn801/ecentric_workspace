# Copyright (c) 2026, eCentric and contributors
"""p036_create_budget_setting_page: create the Budget Setting Web Page at route
/approvals/budget-setting from source (run-once at migrate). Delegates to
budget_setting.page_sync.sync(). Published for UAT; catalog card stays inactive."""
import frappe

from ecentric_workspace.approval_center.budget_setting import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    res = page_sync.sync()
    frappe.logger("approval_center").info("p036_create_budget_setting_page: %s" % (res or {}))
