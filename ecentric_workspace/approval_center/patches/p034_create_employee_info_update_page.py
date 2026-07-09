# Copyright (c) 2026, eCentric and contributors
"""p034_create_employee_info_update_page: create the Employee information update Web Page at route /approvals/employee-information-update from source
(run-once at migrate). Delegates to employee_info_update.page_sync.sync(). Published for UAT;
catalog card stays Coming Soon."""
import frappe

from ecentric_workspace.approval_center.employee_info_update import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    res = page_sync.sync()
    frappe.logger("approval_center").info("p034_create_employee_info_update_page: %s" % (res or {}))
