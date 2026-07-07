# Copyright (c) 2026, eCentric and contributors
"""p015_create_hr_activity_page: create the HR Activity Web Page (run-once at migrate).
Delegates to hr_activity.page_sync.sync() (idempotent). Card stays inactive."""
import frappe

from ecentric_workspace.approval_center.hr_activity import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    frappe.logger("approval_center").info("p015_create_hr_activity_page: %s" % (page_sync.sync() or {}))
