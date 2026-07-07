# Copyright (c) 2026, eCentric and contributors
"""p017_create_livestream_sample_page: create the Livestream Sample Web Page (run-once
at migrate). Delegates to livestream_sample.page_sync.sync() (idempotent)."""
import frappe

from ecentric_workspace.approval_center.livestream_sample import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    frappe.logger("approval_center").info("p017_create_livestream_sample_page: %s" % (page_sync.sync() or {}))
