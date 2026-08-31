# Copyright (c) 2026, eCentric and contributors
"""Re-publish 25 approval feature pages: stored XSS in the copied stepper.

The 31/08 fix for payment_request's stepper (approver names and rejection comments
concatenated into `.step-meta` innerHTML unescaped - p115) was never propagated: the
stepper is not shared JS, every feature carries its own copy in main_section.html,
and 25 of the 26 features still shipped the pre-fix copy. Anyone who could set a
Full Name or type a rejection comment could run script in the browser of anyone
viewing the request - the exact hole already closed on payment_request.

This patch rides the batched source fix (esc() around approver names, rejection
comments, fulfillment handler names on asset/data/document/resignation/system
requests, and the Skipped-approver list on ai_topup - the intentional "Qua han"
span stays raw HTML) and re-syncs all 25 Web Pages in one migrate.

One broken page must not block the other 24: each sync is wrapped individually,
failures are logged via frappe.log_error and re-raised at the end so the Patch Log
does not record a partial run as done.
"""
import importlib

import frappe

FEATURES = [
    "affiliate_bonus",
    "ai_topup",
    "asset_damage_loss",
    "asset_request",
    "budget_setting",
    "compensation_leave",
    "daily_target",
    "data_request",
    "document_request",
    "employee_info_update",
    "employee_referral",
    "hiring_request",
    "hr_activity",
    "late_early_out",
    "lateral_move",
    "leave",
    "livestream_sample",
    "livestream_supplies",
    "outside_work",
    "promotion",
    "purchase_request",
    "resignation",
    "service_referral",
    "special_bonus",
    "system_request",
]

_MOD = "ecentric_workspace.approval_center.features.{}.infrastructure.page_sync"


def execute():
    failed = []
    for feature in FEATURES:
        try:
            page_sync = importlib.import_module(_MOD.format(feature))
            page_sync.sync()
        except Exception:
            failed.append(feature)
            frappe.log_error(
                title="p116 stepper XSS resync failed: %s" % feature,
                message=frappe.get_traceback(),
            )
    if failed:
        raise Exception(
            "p116: %d/%d feature pages failed to resync (%s) - see Error Log; "
            "raising so the Patch Log does not mark this migration as done."
            % (len(failed), len(FEATURES), ", ".join(failed))
        )
