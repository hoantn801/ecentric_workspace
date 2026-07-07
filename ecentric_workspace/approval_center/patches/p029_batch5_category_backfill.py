# Copyright (c) 2026, eCentric and contributors
"""p029_batch5_category_backfill: place the three Batch-5 approval types in their catalog
categories, on sites where p001/p002 already ran (Frappe won't re-run a completed seed patch).
Idempotent, ORM-only, non-destructive: updates only the `category` field of the existing
EC Approval Type rows - never deletes/recreates a row, never touches card_status/route (cards stay
whatever they are; nothing is published here).
  SPECIAL_BONUS     -> OTHERS
  ASSET_DAMAGE_LOSS -> ADMINISTRATION
  HIRING_REQUEST    -> ADMINISTRATION
"""
import frappe

CAT = "EC Approval Category"
TYP = "EC Approval Type"
TARGET = {"SPECIAL_BONUS": "OTHERS", "ASSET_DAMAGE_LOSS": "ADMINISTRATION", "HIRING_REQUEST": "ADMINISTRATION"}


def execute():
    if not frappe.db.exists("DocType", CAT) or not frappe.db.exists("DocType", TYP):
        return
    moved = []
    for code, cat in TARGET.items():
        if not frappe.db.exists(CAT, cat):
            frappe.logger("approval_center").warning("p029: category %s missing; skipping %s (run p001 first)" % (cat, code))
            continue
        frappe.db.set_value(CAT, cat, "is_active", 1)   # ensure visible
        if frappe.db.exists(TYP, code) and frappe.db.get_value(TYP, code, "category") != cat:
            frappe.db.set_value(TYP, code, "category", cat)
            moved.append("%s->%s" % (code, cat))
    frappe.db.commit()
    frappe.logger("approval_center").info("p029_batch5_category_backfill: %s" % (moved or "(none)"))
