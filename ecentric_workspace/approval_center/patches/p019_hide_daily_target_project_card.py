# Copyright (c) 2026, eCentric and contributors
"""p019_hide_daily_target_project_card: hide the duplicate catalog card
'Daily Target Setting - Project Level' (EC Approval Type DAILY_TARGET_PROJECT) by
setting card_status='Disabled'. The live 'Daily Target Setting' card (DAILY_TARGET)
already covers both scopes. Idempotent, ORM-only, non-destructive: does NOT delete
the DAILY_TARGET_PROJECT-V1 process, the DAILY_TARGET card, or any request data."""
import frappe

TYPE = "EC Approval Type"
CODE = "DAILY_TARGET_PROJECT"


def execute():
    if not frappe.db.exists("DocType", TYPE) or not frappe.db.exists(TYPE, CODE):
        return
    if frappe.db.get_value(TYPE, CODE, "card_status") == "Disabled":
        return  # already hidden
    frappe.db.set_value(TYPE, CODE, "card_status", "Disabled")
    frappe.db.commit()
    frappe.logger("approval_center").info("p019: hid duplicate card %s (card_status=Disabled)" % CODE)
