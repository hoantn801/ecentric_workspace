# Copyright (c) 2026, eCentric and contributors
"""Seed EC Approval Type CONTRACT_REVIEW (form thứ 27 — thay SharePoint Contract approval).
Idempotent, non-destructive, same pattern as p018."""
import json
import os

import frappe

DOCTYPE = "EC Approval Type"
CODE = "CONTRACT_REVIEW"
DEFAULTS = {"card_status": "Coming Soon", "process_status": "Building",
            "visibility_mode": "All Internal Users", "legacy_source": "SharePoint", "route": ""}


def _seed_row():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base, "seed", "approval_types_seed.json"), "r", encoding="utf-8") as fh:
        for row in json.load(fh):
            if row.get("approval_code") == CODE:
                return row
    return None


def execute():
    if not frappe.db.exists("DocType", DOCTYPE) or frappe.db.exists(DOCTYPE, CODE):
        return
    row = _seed_row()
    if not row:
        return
    if row.get("category") and not frappe.db.exists("EC Approval Category", row["category"]):
        frappe.logger("approval_center").warning("p116: category %s missing" % row["category"])
        return
    doc = frappe.new_doc(DOCTYPE)
    doc.update(DEFAULTS)
    doc.update(row)
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
