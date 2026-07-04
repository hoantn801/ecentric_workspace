# Copyright (c) 2026, eCentric and contributors
"""p007_sync_ai_topup_page: versioned, idempotent page sync (replaces reliance on
run-once p006). Safe if the page already exists; writes the final B3 HTML."""
import frappe

from ecentric_workspace.approval_center.ai_topup import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    res = page_sync.sync()
    frappe.logger("approval_center").info("p007_sync_ai_topup_page: %s" % res)
