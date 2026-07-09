# Copyright (c) 2026, eCentric and contributors
"""p036_create_service_referral_page: create the Service referral Web Page at route /approvals/service-referral from source
(run-once at migrate). Delegates to service_referral.page_sync.sync(). Published for UAT;
catalog card stays Coming Soon."""
import frappe

from ecentric_workspace.approval_center.service_referral import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    res = page_sync.sync()
    frappe.logger("approval_center").info("p036_create_service_referral_page: %s" % (res or {}))
