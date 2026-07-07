# Copyright (c) 2026, eCentric and contributors
"""p021_backfill_livestream_sample_type: ensure EC Approval Type LIVESTREAM_SAMPLE exists.

Root cause: p018 back-filled LIVESTREAM_SAMPLE from the seed row, but that row's category is
OTHERS - which is created by p020, ORDERED AFTER p018. So p018's fail-closed 'category must
exist' guard skipped the insert and the type was never created on the live DB. p021 runs after
p020 (OTHERS exists), so it can safely ensure the category AND insert the type.

Idempotent, ORM-only, non-destructive. Category OTHERS; card_status Coming Soon (unpublished);
route left empty (publish_livestream_sample_after_uat sets the live route, matching every other
UAT-stage card). No workflow change; never publishes a card."""
import frappe

CAT = "EC Approval Category"
TYP = "EC Approval Type"
CODE = "LIVESTREAM_SAMPLE"
OTHERS = {"category_code": "OTHERS", "category_name": "Others", "icon": "more-horizontal",
          "sort_order": 80, "is_active": 1}
# Same fixed defaults p002 applies to every catalog row.
ROW = {
    "approval_code": CODE,
    "approval_title": "Livestream Sample Request",
    "category": "OTHERS",
    "description": "Request for receiving sample to studio",
    "legacy_template_name": "Livestream Sample Request",
    "sort_order": 70,
    "card_status": "Coming Soon",
    "process_status": "Discovery",
    "visibility_mode": "All Internal Users",
    "legacy_source": "MS Teams",
    "route": "",
}


def execute():
    if not frappe.db.exists("DocType", CAT) or not frappe.db.exists("DocType", TYP):
        return
    # 1) ensure the OTHERS category exists (defensive - p020 normally created it)
    if not frappe.db.exists(CAT, "OTHERS"):
        frappe.new_doc(CAT).update(OTHERS).insert(ignore_permissions=True)
    else:
        frappe.db.set_value(CAT, "OTHERS", "is_active", 1)
    # 2) ensure the LIVESTREAM_SAMPLE type exists
    if frappe.db.exists(TYP, CODE):
        # non-destructive: only correct the category if it drifted; never touch admin edits otherwise
        if frappe.db.get_value(TYP, CODE, "category") != "OTHERS":
            frappe.db.set_value(TYP, CODE, "category", "OTHERS")
        frappe.db.commit()
        return
    frappe.new_doc(TYP).update(ROW).insert(ignore_permissions=True)
    frappe.db.commit()
    frappe.logger("approval_center").info("p021_backfill_livestream_sample_type: created %s (OTHERS, Coming Soon)" % CODE)
