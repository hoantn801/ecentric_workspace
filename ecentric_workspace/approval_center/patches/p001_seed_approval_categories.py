# Copyright (c) 2026, eCentric and contributors
"""p001_seed_approval_categories: idempotent, non-destructive seed of the
Approval Center category catalog (EC Approval Category).

Classification: DATA SEED (post_model_sync). Behaviour contract:
  * INSERT missing categories, keyed by the immutable `category_code`.
  * NEVER overwrite an existing record (admin edits are preserved).
  * NEVER delete unknown / custom categories.
  * Safe to run repeatedly (bench migrate re-runs).

Rollback: non-destructive. To remove seeded rows, delete by the known
category_code set (see approval_center/seed/approval_categories_seed.json).
"""
import json
import os

import frappe

DOCTYPE = "EC Approval Category"


def _seed_path():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "seed", "approval_categories_seed.json")


def execute():
    # Fail-safe: schema must exist (post_model_sync should guarantee this).
    if not frappe.db.exists("DocType", DOCTYPE):
        return

    with open(_seed_path(), "r", encoding="utf-8") as fh:
        rows = json.load(fh)

    created = 0
    for row in rows:
        code = row["category_code"]
        if frappe.db.exists(DOCTYPE, code):
            continue  # non-destructive: preserve existing/edited record
        doc = frappe.new_doc(DOCTYPE)
        doc.update(row)
        doc.insert(ignore_permissions=True)
        created += 1

    frappe.db.commit()
    frappe.logger("approval_center").info(
        "p001_seed_approval_categories: created %d new categories" % created
    )
