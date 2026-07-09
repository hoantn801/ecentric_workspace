# Copyright (c) 2026, eCentric and contributors
"""p038_seed_batch8_types: seed the 2 new Batch-8 EC Approval Type rows (BUDGET_SETTING,
AFFILIATE_BONUS_REQUEST) added to approval_types_seed.json after p002 already ran, and move
PURCHASE_REQUEST into the Finance & Budget category (Payment already there). Idempotent,
non-destructive, ORM-only; new cards stay Coming Soon. Never overwrites an existing row's identity."""
import json
import os

import frappe

TYP = "EC Approval Type"
CAT = "EC Approval Category"
FINANCE = "FINANCE_BUDGET"
NEW = ("BUDGET_SETTING", "AFFILIATE_BONUS_REQUEST")
DEFAULTS = {"card_status": "Coming Soon", "process_status": "Discovery",
            "visibility_mode": "All Internal Users", "legacy_source": "MS Teams", "route": ""}


def _seed_rows():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base, "seed", "approval_types_seed.json"), "r", encoding="utf-8") as fh:
        return {r.get("approval_code"): r for r in json.load(fh)}


def execute():
    if not frappe.db.exists("DocType", TYP):
        return
    rows = _seed_rows()
    # 1) seed the 2 new types (Coming Soon)
    for code in NEW:
        if frappe.db.exists(TYP, code):
            continue
        row = rows.get(code)
        if not row:
            continue
        if row.get("category") and not frappe.db.exists(CAT, row["category"]):
            frappe.logger("approval_center").warning("p038: category %s missing; skipping %s" % (row["category"], code))
            continue
        doc = frappe.new_doc(TYP)
        doc.update(DEFAULTS)
        doc.update(row)
        doc.insert(ignore_permissions=True)
    # 2) move Purchase Request into Finance & Budget (Payment already there)
    if frappe.db.exists(CAT, FINANCE) and frappe.db.exists(TYP, "PURCHASE_REQUEST") \
            and frappe.db.get_value(TYP, "PURCHASE_REQUEST", "category") != FINANCE:
        frappe.db.set_value(TYP, "PURCHASE_REQUEST", "category", FINANCE)
    frappe.db.commit()
    frappe.logger("approval_center").info("p038_seed_batch8_types: seeded %s; PURCHASE_REQUEST -> %s" % (NEW, FINANCE))
