# Copyright (c) 2026, eCentric and contributors
"""p039_disable_legacy_budget_cards: Annual + Monthly budget setting are merged into BUDGET_SETTING,
so the legacy catalog cards ANNUAL_BUDGET / MONTHLY_BUDGET are hidden (card_status = Disabled).
Idempotent, non-destructive: only flips card_status, never deletes a row and never touches any
submitted business/approval records. Safe-guard: only disables a card that is NOT public-Active
(i.e. Coming Soon / UAT / Migrating). If a legacy card is Active (production usage), it is LEFT
UNCHANGED and a warning is logged for manual review."""
import frappe

TYP = "EC Approval Type"
LEGACY = ("ANNUAL_BUDGET", "MONTHLY_BUDGET")


def execute():
    if not frappe.db.exists("DocType", TYP):
        return
    disabled, skipped = [], []
    for code in LEGACY:
        if not frappe.db.exists(TYP, code):
            continue
        status = frappe.db.get_value(TYP, code, "card_status")
        if status == "Active":
            skipped.append(code)   # production usage - do not touch; report for manual review
            frappe.logger("approval_center").warning(
                "p039: %s card is Active - left unchanged; review before disabling (merged into BUDGET_SETTING)." % code)
            continue
        if status != "Disabled":
            frappe.db.set_value(TYP, code, "card_status", "Disabled")
            disabled.append(code)
    frappe.db.commit()
    frappe.logger("approval_center").info(
        "p039_disable_legacy_budget_cards: disabled=%s skipped_active=%s" % (disabled, skipped))
