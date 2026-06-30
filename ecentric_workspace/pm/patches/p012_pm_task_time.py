"""PM v2 - Batch G4.11: optional start/end TIME on Task (app-owned Custom Fields).

Idempotent. Core Task date fields (exp_start_date / exp_end_date) are NOT changed. Adds two
nullable Time custom fields so a task can carry an optional time-of-day alongside its date:

  pm_start_time (Time, after exp_start_date)
  pm_end_time   (Time, after exp_end_date)

Old tasks without a time keep working (null). Validation (time requires its date; end datetime
>= start datetime) lives in the api/tasks.py service layer.
"""

import frappe

_FIELDS = [
    {"fieldname": "pm_start_time", "fieldtype": "Time", "label": "Start Time",
     "insert_after": "exp_start_date"},
    {"fieldname": "pm_end_time", "fieldtype": "Time", "label": "End Time",
     "insert_after": "exp_end_date"},
]


def execute():
    for df in _FIELDS:
        name = "Task-" + df["fieldname"]
        if frappe.db.exists("Custom Field", name):
            continue
        payload = {"doctype": "Custom Field", "dt": "Task"}
        payload.update(df)
        frappe.get_doc(payload).insert(ignore_permissions=True)
