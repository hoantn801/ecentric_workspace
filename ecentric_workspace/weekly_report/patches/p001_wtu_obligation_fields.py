# Copyright (c) 2026, eCentric and contributors
"""WR1A: add the 4 obligation fields to Weekly Team Update.

Idempotent: per-field existence check skips already-installed rows.
Fail-hard: insert errors are logged AND re-raised so a partial schema never
ships. A retry after fixing the root cause is safe (idempotent).

Fields:
  wr_schedule          Link  -> Weekly Report Schedule, read_only
  due_at               Datetime, read_only
  generated_obligation Check default 0, read_only
  obligation_key       Data unique read_only

obligation_key = employee + "::" + week_label (see service._obligation_key).
"""

import frappe


DT = "Weekly Team Update"

FIELDS = [
    {
        "fieldname": "wr_schedule",
        "fieldtype": "Link",
        "options": "Weekly Report Schedule",
        "label": "WR Schedule",
        "read_only": 1,
        "insert_after": "late_submission",
        "description": "Source schedule that pre-created this Weekly Team Update.",
    },
    {
        "fieldname": "due_at",
        "fieldtype": "Datetime",
        "label": "Due At",
        "read_only": 1,
        "insert_after": "wr_schedule",
        "description": "Deadline derived from Department Reporting Window at generation time.",
    },
    {
        "fieldname": "generated_obligation",
        "fieldtype": "Check",
        "label": "Generated Obligation",
        "default": "0",
        "read_only": 1,
        "insert_after": "due_at",
        "description": "1 = pre-created by WR scheduler. Gates the ToDo close guard.",
    },
    {
        "fieldname": "obligation_key",
        "fieldtype": "Data",
        "label": "Obligation Key",
        "unique": 1,
        "read_only": 1,
        "insert_after": "generated_obligation",
        "description": "employee + '::' + week_label. DB unique enforces dedup.",
    },
]


def execute():
    for df in FIELDS:
        name = DT + "-" + df["fieldname"]
        if frappe.db.exists("Custom Field", name):
            continue
        payload = {"doctype": "Custom Field", "dt": DT}
        payload.update(df)
        try:
            frappe.get_doc(payload).insert(ignore_permissions=True)
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                "p001_wtu_obligation_fields: " + df["fieldname"],
            )
            raise
    frappe.clear_cache(doctype=DT)
