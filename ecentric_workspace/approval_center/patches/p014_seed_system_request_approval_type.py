# Copyright (c) 2026, eCentric and contributors
"""p014_seed_system_request_approval_type: seed the single EC Approval Type row for
SYSTEM_REQUEST that was added to approval_types_seed.json after p002 had already run
on earlier deployments (Frappe does not re-run p002). Idempotent, non-destructive,
ORM-only. Uses the exact same DEFAULTS + seed-row pattern as p002. Card stays
Coming Soon (inactive); never overwrites an existing row."""
import json
import os

import frappe

DOCTYPE = "EC Approval Type"
CODE = "SYSTEM_REQUEST"
# Same fixed seed defaults p002 applies to every row.
DEFAULTS = {
    "card_status": "Coming Soon",
    "process_status": "Discovery",
    "visibility_mode": "All Internal Users",
    "legacy_source": "MS Teams",
    "route": "",
}


def _seed_row():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base, "seed", "approval_types_seed.json"), "r", encoding="utf-8") as fh:
        for row in json.load(fh):
            if row.get("approval_code") == CODE:
                return row
    return None


def execute():
    if not frappe.db.exists("DocType", DOCTYPE):
        return
    if frappe.db.exists(DOCTYPE, CODE):
        return  # non-destructive: preserve any existing row / admin edits

    row = _seed_row()
    if not row:
        frappe.logger("approval_center").warning("p014: %s not found in seed file; nothing to do" % CODE)
        return
    # Category must resolve (p001 seeds it); fail-closed if somehow absent.
    if row.get("category") and not frappe.db.exists("EC Approval Category", row["category"]):
        frappe.logger("approval_center").warning(
            "p014: category %s missing; skipping (run p001 first)" % row["category"])
        return

    doc = frappe.new_doc(DOCTYPE)
    doc.update(DEFAULTS)   # fixed defaults first
    doc.update(row)        # identity + category + legacy name + sort_order
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    frappe.logger("approval_center").info("p014_seed_system_request_approval_type: created %s (Coming Soon)" % CODE)
