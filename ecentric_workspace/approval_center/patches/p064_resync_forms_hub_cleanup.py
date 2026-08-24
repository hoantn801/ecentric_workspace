# Copyright (c) 2026, eCentric and contributors
"""Re-sync every Approval Center form page after the hub cleanup.

Two page-level changes ship together (one migrate, one deploy):
  * the per-form tab bar is reduced to 'Tạo yêu cầu' -- 'Yêu cầu của tôi', 'Cần tôi duyệt'
    and 'Chờ Operation xử lý' now live once, for every form, on /approvals/all-requests.
    Every 'back to list' navigation and any stale ?tab= link points at the hub instead.
  * attachment inputs accept MULTIPLE files (uploaded sequentially; a draft is created
    first when needed so every file lands on the record).

Each form's page_sync carries the #144 drift lock, and its BASELINE_SHA256 was bumped in the
same commit (previous value moved into SUPERSEDES_SHA256), so this sync writes exactly once
and then reports 'unchanged'. A page whose live copy drifted elsewhere is refused, not
overwritten. Failure on one form never blocks the others (or the rest of migrate)."""
import frappe

from ecentric_workspace.approval_center.shared.registry import APPROVAL_DEFINITIONS

_MODULE = "ecentric_workspace.approval_center.features.%s.infrastructure.page_sync"


def execute():
    seen, results = set(), {}
    for definition in APPROVAL_DEFINITIONS.values():
        feature = getattr(definition, "feature", "") or ""
        if not feature or feature in seen:
            continue
        seen.add(feature)
        try:
            module = frappe.get_module(_MODULE % feature)
        except Exception:
            continue
        try:
            results[feature] = (module.sync() or {}).get("action")
        except Exception:
            frappe.logger("approval_center").warning("p064: sync failed for %s" % feature)
            results[feature] = "error"
    frappe.logger("approval_center").info("p064 form page resync: %s" % results)
