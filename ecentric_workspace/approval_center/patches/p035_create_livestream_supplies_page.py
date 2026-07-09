# Copyright (c) 2026, eCentric and contributors
"""p035_create_livestream_supplies_page: create the Livestream supplies request Web Page at route /approvals/livestream-supplies from source
(run-once at migrate). Delegates to livestream_supplies.page_sync.sync(). Published for UAT;
catalog card stays Coming Soon."""
import frappe

from ecentric_workspace.approval_center.livestream_supplies import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    res = page_sync.sync()
    frappe.logger("approval_center").info("p035_create_livestream_supplies_page: %s" % (res or {}))
