# Copyright (c) 2026, eCentric and contributors
"""p020_others_category_backfill: ensure the 'Others' catalog category exists and move
Employee Referral + Livestream Sample under it, on sites where p001/p002/p018 already
ran (Frappe won't re-run a completed seed patch). Idempotent, ORM-only, non-destructive:
creates the OTHERS category if missing and sets the two EC Approval Type rows' category
to OTHERS. No workflow/process change; never publishes a card."""
import frappe

CAT = "EC Approval Category"
TYP = "EC Approval Type"
OTHERS = {"category_code": "OTHERS", "category_name": "Others", "icon": "more-horizontal",
          "sort_order": 80, "is_active": 1}
RETARGET = ("EMPLOYEE_REFERRAL", "LIVESTREAM_SAMPLE")


def execute():
    if not frappe.db.exists("DocType", CAT) or not frappe.db.exists("DocType", TYP):
        return
    if not frappe.db.exists(CAT, "OTHERS"):
        doc = frappe.new_doc(CAT)
        doc.update(OTHERS)
        doc.insert(ignore_permissions=True)
    else:
        frappe.db.set_value(CAT, "OTHERS", "is_active", 1)   # ensure visible
    for code in RETARGET:
        if frappe.db.exists(TYP, code) and frappe.db.get_value(TYP, code, "category") != "OTHERS":
            frappe.db.set_value(TYP, code, "category", "OTHERS")
    frappe.db.commit()
    frappe.logger("approval_center").info("p020_others_category_backfill: OTHERS ensured; %s -> OTHERS" % (RETARGET,))
