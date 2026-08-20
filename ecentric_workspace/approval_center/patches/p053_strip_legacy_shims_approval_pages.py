# Copyright (c) 2026, eCentric and contributors
"""Strip leftover Desk-style shims from ALL Approval Center Web Pages (route approvals/*).

The shim POSTs to '/' and pops a false '<Doctype> <name> not found' popup when a request
is opened via its deep link (e.g. from a Teams notification). system_request/resignation
page_sync already strip it on sync, but asset_request (and others) do not, so this one-time
pass cleans every approvals/* Web Page. Meta-driven + non-destructive: strip_legacy_shims
only clears a field whose value contains an unambiguous shim marker (never main_section)."""
import frappe

from ecentric_workspace.approval_center.shared import page_sync as page_sync_util


def execute():
    names = frappe.get_all("Web Page", filters={"route": ["like", "approvals/%"]}, pluck="name")
    stripped = []
    for name in names:
        try:
            res = page_sync_util.strip_legacy_shims(name)
            if res.get("has_legacy_shim"):
                stripped.append(name)
        except Exception:
            frappe.logger("approval_center").warning("p053 strip shim failed: %s" % name)
    frappe.logger("approval_center").info(
        "p053 stripped legacy shim from %d page(s): %s" % (len(stripped), stripped))
