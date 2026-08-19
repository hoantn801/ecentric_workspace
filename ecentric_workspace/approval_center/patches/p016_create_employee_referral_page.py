# Copyright (c) 2026, eCentric and contributors
"""p016_create_employee_referral_page: create the Employee Referral Web Page (run-once
at migrate). Delegates to employee_referral.page_sync.sync() (idempotent)."""
import frappe

from ecentric_workspace.approval_center.features.employee_referral.infrastructure import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    frappe.logger("approval_center").info("p016_create_employee_referral_page: %s" % (page_sync.sync() or {}))
