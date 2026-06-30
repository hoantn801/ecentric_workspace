"""PM v2 - Batch G5.0: Assignment Acceptance schema (app-owned, hardened).

Idempotent. Creates the assignment-request doctype + its append-only audit child table. Same
convention as labels (p009): DocPerm is System Manager READ-ONLY; PM Manager / PM Member get no
generic DocPerm -> all mutation goes through the api/assignment.py service layer.

  PM Assignment Request          (top-level)
  PM Assignment Request Event    (child, append-only audit trail)

open_request_key (hidden Data, UNIQUE): value '<task>::<recipient>' ONLY while status is Pending
or Reschedule Proposed; set to NULL (not '') on Accepted/Rejected/Cancelled so a later legitimate
request for the same (task, recipient) is allowed (MariaDB permits multiple NULLs under a unique
index). open_task_key (hidden Data, UNIQUE) is the canonical 'one OPEN request per TASK' invariant:
value '<task>' while OPEN, NULL otherwise. DB uniqueness + a friendly service error prevent two
concurrent OPEN requests for the same task (any recipient).
"""

import frappe

_PERMS = [
    {"role": "System Manager", "read": 1, "create": 0, "write": 0, "delete": 0},
]
_STATUSES = ["Pending", "Accepted", "Rejected", "Reschedule Proposed", "Cancelled"]


def _ensure_doctype(spec):
    if frappe.db.exists("DocType", spec["name"]):
        return
    frappe.get_doc(spec).insert(ignore_permissions=True)


def _ensure_unique_field(dt, fieldname, label):
    """Recovery-safe + idempotent: add the hidden/unique/read_only column ONLY if the DocType
    exists but genuinely LACKS it (meta.has_field sees DocFields AND Custom Fields). On a fresh
    create the column is already in the definition -> never insert a duplicate (the p009 lesson)."""
    if not frappe.db.exists("DocType", dt):
        return
    frappe.clear_cache(doctype=dt)
    if frappe.get_meta(dt, cached=False).has_field(fieldname):
        return
    frappe.get_doc({
        "doctype": "Custom Field", "dt": dt, "fieldname": fieldname, "fieldtype": "Data",
        "label": label, "hidden": 1, "unique": 1, "read_only": 1, "no_copy": 1,
    }).insert(ignore_permissions=True)


def execute():
    # child FIRST (referenced by the parent's Table field)
    _ensure_doctype({
        "doctype": "DocType", "name": "PM Assignment Request Event",
        "module": "Ecentric Workspace", "custom": 1, "istable": 1, "track_changes": 1,
        "fields": [
            {"fieldname": "event_time", "fieldtype": "Datetime", "label": "Time",
             "in_list_view": 1, "read_only": 1},
            {"fieldname": "actor", "fieldtype": "Link", "label": "Actor", "options": "User",
             "in_list_view": 1, "read_only": 1},
            {"fieldname": "action", "fieldtype": "Data", "label": "Action",
             "in_list_view": 1, "read_only": 1},
            {"fieldname": "detail", "fieldtype": "Small Text", "label": "Detail", "read_only": 1},
            {"fieldname": "old_start", "fieldtype": "Datetime", "label": "Old Start", "read_only": 1},
            {"fieldname": "old_end", "fieldtype": "Datetime", "label": "Old End", "read_only": 1},
            {"fieldname": "new_start", "fieldtype": "Datetime", "label": "New Start", "read_only": 1},
            {"fieldname": "new_end", "fieldtype": "Datetime", "label": "New End", "read_only": 1},
        ],
    })

    _ensure_doctype({
        "doctype": "DocType", "name": "PM Assignment Request",
        "module": "Ecentric Workspace", "custom": 1, "track_changes": 1,
        "autoname": "hash", "permissions": _PERMS,
        "fields": [
            {"fieldname": "task", "fieldtype": "Link", "label": "Task", "options": "Task",
             "reqd": 1, "in_list_view": 1},
            {"fieldname": "recipient", "fieldtype": "Link", "label": "Recipient", "options": "User",
             "reqd": 1, "in_list_view": 1},
            {"fieldname": "requested_by", "fieldtype": "Link", "label": "Requested By",
             "options": "User", "reqd": 1, "read_only": 1, "in_list_view": 1},
            {"fieldname": "status", "fieldtype": "Select", "label": "Status",
             "options": "\n".join(_STATUSES), "default": "Pending", "in_list_view": 1,
             "read_only": 1},
            {"fieldname": "proposed_start", "fieldtype": "Datetime", "label": "Proposed Start"},
            {"fieldname": "proposed_end", "fieldtype": "Datetime", "label": "Proposed End"},
            {"fieldname": "message", "fieldtype": "Small Text", "label": "Message"},
            {"fieldname": "response_reason", "fieldtype": "Small Text", "label": "Response Reason",
             "read_only": 1},
            {"fieldname": "counter_start", "fieldtype": "Datetime", "label": "Counter Start",
             "read_only": 1},
            {"fieldname": "counter_end", "fieldtype": "Datetime", "label": "Counter End",
             "read_only": 1},
            {"fieldname": "decided_at", "fieldtype": "Datetime", "label": "Decided At",
             "read_only": 1},
            {"fieldname": "decided_by", "fieldtype": "Link", "label": "Decided By",
             "options": "User", "read_only": 1},
            {"fieldname": "open_request_key", "fieldtype": "Data", "label": "Open Request Key",
             "hidden": 1, "unique": 1, "read_only": 1, "no_copy": 1},
            {"fieldname": "open_task_key", "fieldtype": "Data", "label": "Open Task Key",
             "hidden": 1, "unique": 1, "read_only": 1, "no_copy": 1},
            {"fieldname": "events", "fieldtype": "Table", "label": "Events",
             "options": "PM Assignment Request Event"},
        ],
    })

    # Safety net for a pre-existing (older / partially migrated) request DocType lacking a key.
    _ensure_unique_field("PM Assignment Request", "open_request_key", "Open Request Key")
    _ensure_unique_field("PM Assignment Request", "open_task_key", "Open Task Key")
