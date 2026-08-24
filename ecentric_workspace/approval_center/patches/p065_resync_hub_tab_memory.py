# Copyright (c) 2026, eCentric and contributors
"""Re-sync the hub + every form page after adding tab memory.

The hub now keeps the active tab in the URL (?box=) and passes it on when opening a request
(?from=<tab>); each form's 'Danh sách' button reads that and returns to the SAME tab instead
of always landing on 'Tất cả'. Both sides ship together, so both pages are re-synced here.
Drift-locked page_sync: each BASELINE_SHA256 was bumped in the same commit, so this writes
once then reports 'unchanged'; a page that drifted elsewhere is refused, not overwritten."""
import frappe

from ecentric_workspace.approval_center.shared.registry import APPROVAL_DEFINITIONS
from ecentric_workspace.approval_center.ui.all_requests import page_sync as hub_page_sync

_MODULE = "ecentric_workspace.approval_center.features.%s.infrastructure.page_sync"


def execute():
    try:
        hub_page_sync.sync()
    except Exception:
        frappe.logger("approval_center").warning("p065: hub sync failed")
    seen = set()
    for definition in APPROVAL_DEFINITIONS.values():
        feature = getattr(definition, "feature", "") or ""
        if not feature or feature in seen:
            continue
        seen.add(feature)
        try:
            frappe.get_module(_MODULE % feature).sync()
        except Exception:
            frappe.logger("approval_center").warning("p065: sync failed for %s" % feature)
