"""PM v2 - Batch G1: ERP-grade checklist schema foundation.

Idempotent. Creates 3 custom DocTypes + 2 Custom Fields. **INERT** -- nothing reads
or writes these yet; no behaviour change. G2+ wires generation / modal / risk.

  - PM Checklist Template        (top-level)  -> reusable routine definition
  - PM Checklist Template Item   (child)      -> template items (idx = order)
  - PM Task Checklist Item       (child)      -> per-task checklist instance items
  - PM Recurrence.checklist_template (Link)   -> a rule may reference a template
  - Task.pm_checklist (Table)                 -> the task's checklist instance

Same convention as p003/p004 (custom DocType via patch). Safe to run multiple times.
Inert until listed in patches.txt + migrate.
"""

import frappe

_PERMS = [
    {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1},
    {"role": "PM Manager", "read": 1, "write": 1, "create": 1, "delete": 1},
    {"role": "PM Member", "read": 1, "write": 1, "create": 1, "delete": 1},
]


def _ensure_doctype(spec):
    if frappe.db.exists("DocType", spec["name"]):
        return
    frappe.get_doc(spec).insert(ignore_permissions=True)


def _ensure_custom_field(dt, df):
    name = dt + "-" + df["fieldname"]
    if frappe.db.exists("Custom Field", name):
        return
    payload = {"doctype": "Custom Field", "dt": dt}
    payload.update(df)
    frappe.get_doc(payload).insert(ignore_permissions=True)


def execute():
    # Child DocTypes must exist BEFORE the parents/fields that reference them.

    # 1) child: PM Checklist Template Item
    _ensure_doctype({
        "doctype": "DocType", "name": "PM Checklist Template Item",
        "module": "Ecentric Workspace", "custom": 1, "istable": 1, "track_changes": 1,
        "fields": [
            {"fieldname": "item_label", "fieldtype": "Data", "label": "Item",
             "reqd": 1, "in_list_view": 1},
            {"fieldname": "is_required", "fieldtype": "Check", "label": "Required",
             "default": "1", "in_list_view": 1},
            {"fieldname": "item_description", "fieldtype": "Small Text", "label": "Description"},
        ],
    })

    # 2) child: PM Task Checklist Item
    _ensure_doctype({
        "doctype": "DocType", "name": "PM Task Checklist Item",
        "module": "Ecentric Workspace", "custom": 1, "istable": 1, "track_changes": 1,
        "fields": [
            {"fieldname": "item_label", "fieldtype": "Data", "label": "Item",
             "reqd": 1, "in_list_view": 1},
            {"fieldname": "is_required", "fieldtype": "Check", "label": "Required",
             "default": "1", "in_list_view": 1},
            {"fieldname": "is_done", "fieldtype": "Check", "label": "Done",
             "default": "0", "in_list_view": 1},
            {"fieldname": "completed_by", "fieldtype": "Link", "label": "Completed By",
             "options": "User", "read_only": 1},
            {"fieldname": "completed_at", "fieldtype": "Datetime", "label": "Completed At",
             "read_only": 1},
            {"fieldname": "source_template_item", "fieldtype": "Data",
             "label": "Source Template Item", "read_only": 1},
        ],
    })

    # 3) top-level: PM Checklist Template
    _ensure_doctype({
        "doctype": "DocType", "name": "PM Checklist Template",
        "module": "Ecentric Workspace", "custom": 1, "track_changes": 1,
        "autoname": "field:template_name", "title_field": "template_name",
        "fields": [
            {"fieldname": "template_name", "fieldtype": "Data", "label": "Template Name",
             "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "department", "fieldtype": "Link", "label": "Department",
             "options": "Department"},
            {"fieldname": "is_active", "fieldtype": "Check", "label": "Active",
             "default": "1", "in_list_view": 1},
            {"fieldname": "description", "fieldtype": "Small Text", "label": "Description"},
            {"fieldname": "items", "fieldtype": "Table", "label": "Items",
             "options": "PM Checklist Template Item"},
        ],
        "permissions": _PERMS,
    })

    # 4) custom fields (additive; reference the child/template DocTypes above)
    _ensure_custom_field("PM Recurrence", {
        "fieldname": "checklist_template", "fieldtype": "Link", "label": "Checklist Template",
        "options": "PM Checklist Template", "insert_after": "status",
    })
    _ensure_custom_field("Task", {
        "fieldname": "pm_checklist", "fieldtype": "Table", "label": "PM Checklist",
        "options": "PM Task Checklist Item", "insert_after": "description",
    })

    frappe.clear_cache()
