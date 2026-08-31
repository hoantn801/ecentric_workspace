# Copyright (c) 2026, eCentric and contributors
"""Create/refresh the /approvals/contract-review Web Page from source."""
import frappe

from ecentric_workspace.approval_center.features.contract_review.infrastructure import page_sync


def execute():
    try:
        frappe.log_error("p117 contract-review sync=%s" % (page_sync.sync() or {}).get("action"),
                         "p117 create page")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p117 create page failed")
