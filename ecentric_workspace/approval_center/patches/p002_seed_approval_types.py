# Copyright (c) 2026, eCentric and contributors
"""p002_seed_approval_types: idempotent, non-destructive seed of the 19 current
MS Teams approval templates into the Approval Center registry (EC Approval Type).

Runs AFTER p001 (categories must exist for the `category` Link). Behaviour:
  * INSERT missing types, keyed by the immutable `approval_code`.
  * Every seeded row uses the fixed B1 defaults below (no active route yet).
  * NEVER overwrite an existing record (admin edits are preserved).
  * NEVER delete unknown / custom types.
  * Safe to run repeatedly.

Rollback: non-destructive. To remove seeded rows, delete by the known
approval_code set (see approval_center/seed/approval_types_seed.json).
"""
import json
import os

import frappe

DOCTYPE = "EC Approval Type"

# Fixed B1 seed defaults for ALL 19 rows (locked decision).
DEFAULTS = {
    "card_status": "Coming Soon",
    "process_status": "Discovery",
    "visibility_mode": "All Internal Users",
    "legacy_source": "MS Teams",
    "route": "",
}


def _seed_path():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "seed", "approval_types_seed.json")


def execute():
    if not frappe.db.exists("DocType", DOCTYPE):
        return

    with open(_seed_path(), "r", encoding="utf-8") as fh:
        rows = json.load(fh)

    created = 0
    for row in rows:
        code = row["approval_code"]
        if frappe.db.exists(DOCTYPE, code):
            continue  # non-destructive
        doc = frappe.new_doc(DOCTYPE)
        doc.update(DEFAULTS)   # fixed defaults first
        doc.update(row)        # identity + category + legacy name + sort_order
        doc.insert(ignore_permissions=True)
        created += 1

    frappe.db.commit()
    frappe.logger("approval_center").info(
        "p002_seed_approval_types: created %d new approval types" % created
    )
