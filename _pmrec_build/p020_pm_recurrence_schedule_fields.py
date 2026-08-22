"""PM v2 - 2026-08-06 (p020): MS-Teams-style recurrence schedule fields.

Idempotent, additive. Adds to PM Recurrence:
  - interval     Int  (default 1)  -> "repeat every N" (days/weeks/months)
  - weekly_days  Small Text (JSON) -> selected weekdays for Weekly (Mon=0..Sun=6); blank = start weekday
  - monthly_day  Int              -> day-of-month for Monthly; blank = start day-of-month

No behaviour change for existing rules (interval defaults to 1, weekly_days/monthly_day blank ->
engine falls back to the start weekday / start day, i.e. the prior fixed-interval behaviour).
"""

import frappe


def _ensure_custom_field(dt, df):
    name = dt + "-" + df["fieldname"]
    if frappe.db.exists("Custom Field", name):
        return
    payload = {"doctype": "Custom Field", "dt": dt}
    payload.update(df)
    frappe.get_doc(payload).insert(ignore_permissions=True)


def execute():
    _ensure_custom_field("PM Recurrence", {
        "fieldname": "interval", "fieldtype": "Int", "label": "Repeat Every (N)",
        "default": "1", "insert_after": "frequency"})
    _ensure_custom_field("PM Recurrence", {
        "fieldname": "weekly_days", "fieldtype": "Small Text", "label": "Weekly Days (JSON, Mon=0)",
        "insert_after": "interval"})
    _ensure_custom_field("PM Recurrence", {
        "fieldname": "monthly_day", "fieldtype": "Int", "label": "Monthly Day-of-Month",
        "insert_after": "weekly_days"})
    frappe.clear_cache()
