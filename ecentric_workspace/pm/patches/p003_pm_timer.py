"""PM v2 - create the `PM Timer` DocType (active worktime timer state).

Idempotent. Minimal custom DocType; autoname=field:user + unique user -> exactly
one active timer per user. Holds transient running state only; durable worktime
is the native Timesheet created on Stop.

Inert until listed in patches.txt + migrate.
"""

import frappe


def execute():
    if frappe.db.exists("DocType", "PM Timer"):
        return
    frappe.get_doc({
        "doctype": "DocType",
        "name": "PM Timer",
        "module": "Ecentric Workspace",
        "custom": 1,
        "autoname": "field:user",
        "track_changes": 1,
        "fields": [
            {"fieldname": "user", "fieldtype": "Link", "label": "User",
             "options": "User", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "task", "fieldtype": "Link", "label": "Task",
             "options": "Task", "reqd": 1, "in_list_view": 1},
            {"fieldname": "project", "fieldtype": "Link", "label": "Project",
             "options": "Project"},
            {"fieldname": "start_time", "fieldtype": "Datetime", "label": "Start Time"},
            {"fieldname": "accumulated_seconds", "fieldtype": "Int",
             "label": "Accumulated Seconds", "default": "0"},
            {"fieldname": "status", "fieldtype": "Select", "label": "Status",
             "options": "Running\nPaused", "default": "Running", "in_list_view": 1},
        ],
        "permissions": [
            {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1},
            {"role": "PM Manager", "read": 1, "write": 1, "create": 1, "delete": 1},
            {"role": "PM Member", "read": 1, "write": 1, "create": 1, "delete": 1},
        ],
    }).insert(ignore_permissions=True)
    frappe.clear_cache()
