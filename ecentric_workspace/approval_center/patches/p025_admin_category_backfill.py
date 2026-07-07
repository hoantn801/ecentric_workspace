# Copyright (c) 2026, eCentric and contributors
"""p025_admin_category_backfill: move the three Batch-4 approval types from the HR catalog
category to Administration, on sites where p001/p002 already ran (Frappe won't re-run a
completed seed patch). Idempotent, ORM-only, non-destructive: it only updates the `category`
field of the existing EC Approval Type rows - it never deletes/recreates a row and never
touches card_status/route (cards stay whatever they are; not published here)."""
import frappe

CAT = "EC Approval Category"
TYP = "EC Approval Type"
ADMIN = "ADMINISTRATION"
RETARGET = ("RESIGNATION", "PROMOTION_REQUEST", "LATERAL_MOVE")


def execute():
    if not frappe.db.exists("DocType", CAT) or not frappe.db.exists("DocType", TYP):
        return
    if not frappe.db.exists(CAT, ADMIN):
        # Administration is seeded by p001; if somehow absent, fail-closed (do not invent it here).
        frappe.logger("approval_center").warning("p025: category %s missing; skipping (run p001 first)" % ADMIN)
        return
    frappe.db.set_value(CAT, ADMIN, "is_active", 1)   # ensure visible
    moved = []
    for code in RETARGET:
        if frappe.db.exists(TYP, code) and frappe.db.get_value(TYP, code, "category") != ADMIN:
            frappe.db.set_value(TYP, code, "category", ADMIN)
            moved.append(code)
    frappe.db.commit()
    frappe.logger("approval_center").info("p025_admin_category_backfill: %s -> %s" % (moved or "(none)", ADMIN))
