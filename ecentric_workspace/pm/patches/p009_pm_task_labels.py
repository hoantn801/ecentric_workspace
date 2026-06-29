"""PM v2 - Batch G4.9: reusable task labels (schema foundation, hardened).

Idempotent. Creates 2 custom DocTypes. Same patch convention as p003/p004/p005.

SECURITY: DocPerm is System Manager READ-ONLY (no create/write/delete). PM Manager / PM Member do
NOT get generic DocPerm on these DocTypes -> they can ONLY act through the whitelisted
ecentric_workspace.pm.api.labels service (which runs require_pm_access + can_view_task +
leader/terminal/active/color checks BEFORE any ignore_permissions write). This prevents a
PM user from using the generic Frappe CRUD endpoints to create/rename/archive labels, attach
to a terminal/inactive task, or forge duplicate assignments.

DB-backed uniqueness (race-safe; service layer alone has a TOCTOU window):
  - PM Task Label.normalized_name  (hidden, unique) = label_name.strip().casefold()
  - PM Task Label Assignment.assignment_key (hidden, unique) = "<task>::<label>"
"""

import frappe

# System Manager gets READ-ONLY generic DocPerm; create/write/delete are 0 so EVERY mutation
# (incl. a System Manager using the generic Frappe CRUD) must go through api/labels.py, which
# runs the full guard chain before its ignore_permissions writes. PM Manager / PM Member get no
# generic DocPerm at all. Hard-delete of an in-use label is additionally blocked by the
# pm_label_before_delete hook (even for Administrator / generic delete).
_PERMS = [
    {"role": "System Manager", "read": 1, "create": 0, "write": 0, "delete": 0},
]

COLOR_KEYS = ["gray", "blue", "cyan", "green", "yellow", "orange", "red", "purple", "pink"]


def _ensure_doctype(spec):
    if frappe.db.exists("DocType", spec["name"]):
        return
    frappe.get_doc(spec).insert(ignore_permissions=True)


def _ensure_field(dt, df):
    """Add a field to an already-existing DocType (idempotent) via Custom Field, so a re-run
    after the DocType exists still installs the unique hidden columns."""
    name = dt + "-" + df["fieldname"]
    if frappe.db.exists("Custom Field", name):
        return
    payload = {"doctype": "Custom Field", "dt": dt}
    payload.update(df)
    frappe.get_doc(payload).insert(ignore_permissions=True)


def execute():
    _ensure_doctype({
        "doctype": "DocType", "name": "PM Task Label",
        "module": "Ecentric Workspace", "custom": 1, "track_changes": 1,
        "autoname": "hash", "permissions": _PERMS,
        "fields": [
            {"fieldname": "label_name", "fieldtype": "Data", "label": "Label",
             "reqd": 1, "in_list_view": 1},
            {"fieldname": "color_key", "fieldtype": "Select", "label": "Color",
             "options": "\n".join(COLOR_KEYS), "default": "gray", "reqd": 1, "in_list_view": 1},
            {"fieldname": "is_active", "fieldtype": "Check", "label": "Active",
             "default": "1", "in_list_view": 1},
            {"fieldname": "description", "fieldtype": "Small Text", "label": "Description"},
            {"fieldname": "normalized_name", "fieldtype": "Data", "label": "Normalized Name",
             "hidden": 1, "unique": 1, "read_only": 1, "no_copy": 1},
        ],
    })

    _ensure_doctype({
        "doctype": "DocType", "name": "PM Task Label Assignment",
        "module": "Ecentric Workspace", "custom": 1, "track_changes": 1,
        "autoname": "hash", "permissions": _PERMS,
        "fields": [
            {"fieldname": "task", "fieldtype": "Link", "label": "Task",
             "options": "Task", "reqd": 1, "in_list_view": 1},
            {"fieldname": "label", "fieldtype": "Link", "label": "Label",
             "options": "PM Task Label", "reqd": 1, "in_list_view": 1},
            {"fieldname": "assignment_key", "fieldtype": "Data", "label": "Assignment Key",
             "hidden": 1, "unique": 1, "read_only": 1, "no_copy": 1},
        ],
    })

    # If the DocTypes pre-existed (created by an earlier version of this patch without the
    # unique columns), add them now so the DB index is always present.
    _ensure_field("PM Task Label", {
        "fieldname": "normalized_name", "fieldtype": "Data", "label": "Normalized Name",
        "hidden": 1, "unique": 1, "read_only": 1, "no_copy": 1})
    _ensure_field("PM Task Label Assignment", {
        "fieldname": "assignment_key", "fieldtype": "Data", "label": "Assignment Key",
        "hidden": 1, "unique": 1, "read_only": 1, "no_copy": 1})
