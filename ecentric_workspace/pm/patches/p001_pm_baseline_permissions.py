"""PM1-T03 - baseline DocPerm for PM roles on Project and Task.

Idempotent: re-running is safe (add_permission no-ops if the rule exists,
update_permission_property just re-sets the value).

Inert until registered in patches.txt (activation step) + migrate. This file
alone changes nothing.

Role rights (permlevel 0):
  PM Manager -> read, write, create, delete, report, export   (admin of PM data)
  PM Member  -> read, write, create                           (no delete)

Row-level visibility is handled separately by
ecentric_workspace.pm.permissions.* (permission_query_conditions).
System Manager keeps full native access.
"""

import frappe
from frappe.permissions import add_permission, update_permission_property


def execute():
    matrix = {
        "Project": {
            "PM Manager": {"read": 1, "write": 1, "create": 1, "delete": 1, "report": 1, "export": 1},
            "PM Member": {"read": 1, "write": 1, "create": 1},
        },
        "Task": {
            "PM Manager": {"read": 1, "write": 1, "create": 1, "delete": 1, "report": 1, "export": 1},
            "PM Member": {"read": 1, "write": 1, "create": 1},
        },
    }
    for doctype, roles in matrix.items():
        for role, rights in roles.items():
            add_permission(doctype, role, 0)
            for ptype, value in rights.items():
                update_permission_property(doctype, role, 0, ptype, value, validate=False)
    frappe.clear_cache()
