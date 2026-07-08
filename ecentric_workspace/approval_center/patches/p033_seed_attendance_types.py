# Copyright (c) 2026, eCentric and contributors
"""p033_seed_attendance_types: seed the three Batch-6 Attendance EC Approval Type rows
(LEAVE_REQUEST, LATE_EARLY_OUT, COMPENSATION_LEAVE) that were added to approval_types_seed.json
after p002 had already run on earlier deployments (Frappe won't re-run p002). Idempotent,
non-destructive, ORM-only; uses the same fixed defaults + seed-row pattern as p002. Cards stay
Coming Soon (inactive); never overwrites an existing row."""
import json
import os

import frappe

DOCTYPE = "EC Approval Type"
CODES = ("LEAVE_REQUEST", "LATE_EARLY_OUT", "COMPENSATION_LEAVE")
DEFAULTS = {"card_status": "Coming Soon", "process_status": "Discovery",
            "visibility_mode": "All Internal Users", "legacy_source": "MS Teams", "route": ""}


def _seed_rows():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base, "seed", "approval_types_seed.json"), "r", encoding="utf-8") as fh:
        return {r.get("approval_code"): r for r in json.load(fh)}


def execute():
    if not frappe.db.exists("DocType", DOCTYPE):
        return
    rows = _seed_rows()
    for code in CODES:
        if frappe.db.exists(DOCTYPE, code):
            continue  # non-destructive
        row = rows.get(code)
        if not row:
            frappe.logger("approval_center").warning("p033: %s not in seed file; skipping" % code)
            continue
        if row.get("category") and not frappe.db.exists("EC Approval Category", row["category"]):
            frappe.logger("approval_center").warning("p033: category %s missing; skipping %s" % (row["category"], code))
            continue
        doc = frappe.new_doc(DOCTYPE)
        doc.update(DEFAULTS)
        doc.update(row)
        doc.insert(ignore_permissions=True)
    frappe.db.commit()
    frappe.logger("approval_center").info("p033_seed_attendance_types: ensured %s (Coming Soon)" % (CODES,))
