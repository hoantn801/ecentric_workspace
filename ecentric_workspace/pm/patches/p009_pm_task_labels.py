"""PM v2 - Batch G4.9: reusable task labels (schema foundation, hardened + idempotent).

Idempotent + recovery-safe. Creates 2 custom DocTypes. Same patch convention as p003/p004/p005.

SECURITY: DocPerm is System Manager READ-ONLY (no create/write/delete). PM Manager / PM Member
do NOT get generic DocPerm -> they can ONLY act through the whitelisted
ecentric_workspace.pm.api.labels service (full guard chain before any ignore_permissions write).
Hard-delete of an in-use label is blocked by the pm_label_before_delete hook (even Administrator).

DB-backed uniqueness (race-safe; service layer alone has a TOCTOU window). The unique columns are
declared INSIDE each DocType definition, so a fresh create installs them with the right props:
  - PM Task Label.normalized_name  (hidden, read_only, unique) = label_name.strip().casefold()
  - PM Task Label Assignment.assignment_key (hidden, read_only, unique) = "<task>::<label>"

IDEMPOTENCY/RECOVERY: _ensure_unique_field only adds a Custom Field when the DocType EXISTS but
GENUINELY LACKS the column (checked via meta.has_field, which sees DocFields AND Custom Fields).
On a fresh create the column already exists as a DocField -> we never insert a duplicate (the bug
that produced "A field with the name normalized_name already exists"). Running this patch twice,
or after a partial/rolled-back migrate, is a no-op.
"""

import frappe

# System Manager READ-ONLY; all mutation goes through api/labels.py (ignore_permissions + guards).
_PERMS = [
    {"role": "System Manager", "read": 1, "create": 0, "write": 0, "delete": 0},
]

COLOR_KEYS = ["gray", "blue", "cyan", "green", "yellow", "orange", "red", "purple", "pink"]


def _ensure_doctype(spec):
    """Create the DocType only if its record does not already exist. Frappe syncs the DB table
    on insert, so this is safe even if a previous partial run left the table behind."""
    if frappe.db.exists("DocType", spec["name"]):
        return
    frappe.get_doc(spec).insert(ignore_permissions=True)


def _ensure_unique_field(dt, fieldname, label):
    """Add the hidden/read_only/unique column ONLY when the DocType exists but lacks the field.
    meta.has_field() sees the DocField (from a fresh definition) AND any prior Custom Field, so we
    never create a duplicate. No-op on fresh create (field already present) and on re-runs."""
    if not frappe.db.exists("DocType", dt):
        return
    frappe.clear_cache(doctype=dt)
    if frappe.get_meta(dt, cached=False).has_field(fieldname):
        return  # already present (DocField or Custom Field) -> reconcile = leave it; no duplicate
    frappe.get_doc({
        "doctype": "Custom Field", "dt": dt, "fieldname": fieldname, "fieldtype": "Data",
        "label": label, "hidden": 1, "unique": 1, "read_only": 1, "no_copy": 1,
    }).insert(ignore_permissions=True)


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

    # Safety net ONLY for a pre-existing DocType that lacks the unique column (e.g. created by an
    # older build). No-op on a fresh create and on every re-run.
    _ensure_unique_field("PM Task Label", "normalized_name", "Normalized Name")
    _ensure_unique_field("PM Task Label Assignment", "assignment_key", "Assignment Key")
