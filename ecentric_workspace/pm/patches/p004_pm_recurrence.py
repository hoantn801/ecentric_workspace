"""PM v2 - create the `PM Recurrence` DocType (recurring task rules).

Idempotent. Custom DocType, no native Auto Repeat, native Task untouched.
Frequencies: Daily / Weekly / Biweekly / Monthly. End conditions (end_date,
max_occurrences) are optional; blank = run until Paused/Cancelled.

Inert until listed in patches.txt + migrate.
"""

import frappe


def execute():
    if frappe.db.exists("DocType", "PM Recurrence"):
        return
    frappe.get_doc({
        "doctype": "DocType",
        "name": "PM Recurrence",
        "module": "Ecentric Workspace",
        "custom": 1,
        "track_changes": 1,
        "fields": [
            {"fieldname": "source_task", "fieldtype": "Link", "label": "Source Task",
             "options": "Task", "reqd": 1, "in_list_view": 1},
            {"fieldname": "project", "fieldtype": "Link", "label": "Project", "options": "Project"},
            {"fieldname": "frequency", "fieldtype": "Select", "label": "Frequency",
             "options": "Daily\nWeekly\nBiweekly\nMonthly", "reqd": 1, "in_list_view": 1},
            {"fieldname": "start_date", "fieldtype": "Date", "label": "Start Date"},
            {"fieldname": "next_run_date", "fieldtype": "Date", "label": "Next Run Date", "in_list_view": 1},
            {"fieldname": "end_date", "fieldtype": "Date", "label": "End Date"},
            {"fieldname": "max_occurrences", "fieldtype": "Int", "label": "Max Occurrences", "default": "0"},
            {"fieldname": "occurrences_done", "fieldtype": "Int", "label": "Occurrences Done", "default": "0"},
            {"fieldname": "last_task", "fieldtype": "Link", "label": "Last Generated Task", "options": "Task"},
            {"fieldname": "last_run_date", "fieldtype": "Date", "label": "Last Run Date"},
            {"fieldname": "status", "fieldtype": "Select", "label": "Status",
             "options": "Active\nPaused\nCompleted\nCancelled", "default": "Active", "in_list_view": 1},
        ],
        "permissions": [
            {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1},
            {"role": "PM Manager", "read": 1, "write": 1, "create": 1, "delete": 1},
            {"role": "PM Member", "read": 1, "write": 1, "create": 1, "delete": 1},
        ],
    }).insert(ignore_permissions=True)
    frappe.clear_cache()
