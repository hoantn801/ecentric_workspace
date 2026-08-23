"""PM v2 - Redesign 2026-08-04: make PM Recurrence SELF-CONTAINED (Cách 2).

Schema-only, idempotent, INERT until the backfill patch (p018) runs. Adds:
  - child DocType  PM Recurrence Checklist Item   (item_label, is_required)
  - child DocType  PM Recurrence Subtask          (subject, description, priority, assignees)
  - Custom Fields on PM Recurrence: the template moved off `source_task` onto the rule itself
    (template_subject/description/priority/assignees/start_time/end_time/duration_days,
     pm_checklist_items table, pm_subtasks table, template_labels).
  - Property Setter relaxing PM Recurrence.source_task to NOT required (new self-contained rules
    do not use it; it is kept for audit/rollback and migrated by p018).

Same convention as p004/p005 (custom DocType via patch). Safe to run multiple times.
"""

import frappe

_PERMS = [
    {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1},
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


def _ensure_property_setter(dt, fieldname, prop, value, proptype):
    name = "{0}-{1}-{2}".format(dt, fieldname, prop)
    if frappe.db.exists("Property Setter", name):
        return
    frappe.make_property_setter({
        "doctype": dt, "fieldname": fieldname, "property": prop,
        "value": value, "property_type": proptype,
    }, ignore_validate=True)


def execute():
    # 1) child: PM Recurrence Checklist Item
    _ensure_doctype({
        "doctype": "DocType", "name": "PM Recurrence Checklist Item",
        "module": "Ecentric Workspace", "custom": 1, "istable": 1, "track_changes": 1,
        "fields": [
            {"fieldname": "item_label", "fieldtype": "Data", "label": "Item",
             "reqd": 1, "in_list_view": 1},
            {"fieldname": "is_required", "fieldtype": "Check", "label": "Required",
             "default": "1", "in_list_view": 1},
        ],
        "permissions": _PERMS,
    })

    # 2) child: PM Recurrence Subtask (one level; no nested parent)
    _ensure_doctype({
        "doctype": "DocType", "name": "PM Recurrence Subtask",
        "module": "Ecentric Workspace", "custom": 1, "istable": 1, "track_changes": 1,
        "fields": [
            {"fieldname": "subject", "fieldtype": "Data", "label": "Subject",
             "reqd": 1, "in_list_view": 1},
            {"fieldname": "priority", "fieldtype": "Select", "label": "Priority",
             "options": "\nLow\nMedium\nHigh\nUrgent", "in_list_view": 1},
            {"fieldname": "description", "fieldtype": "Small Text", "label": "Description"},
            {"fieldname": "assignees", "fieldtype": "Small Text", "label": "Assignees (JSON)"},
        ],
        "permissions": _PERMS,
    })

    # 3) Custom Fields on PM Recurrence (the self-contained template)
    _ensure_custom_field("PM Recurrence", {
        "fieldname": "template_subject", "fieldtype": "Data", "label": "Template Subject",
        "insert_after": "status"})
    _ensure_custom_field("PM Recurrence", {
        "fieldname": "template_description", "fieldtype": "Text", "label": "Template Description",
        "insert_after": "template_subject"})
    _ensure_custom_field("PM Recurrence", {
        "fieldname": "template_priority", "fieldtype": "Select", "label": "Template Priority",
        "options": "\nLow\nMedium\nHigh\nUrgent", "insert_after": "template_description"})
    _ensure_custom_field("PM Recurrence", {
        "fieldname": "template_assignees", "fieldtype": "Small Text",
        "label": "Template Assignees (JSON)", "insert_after": "template_priority"})
    _ensure_custom_field("PM Recurrence", {
        "fieldname": "template_start_time", "fieldtype": "Data", "label": "Template Start Time",
        "insert_after": "template_assignees"})
    _ensure_custom_field("PM Recurrence", {
        "fieldname": "template_end_time", "fieldtype": "Data", "label": "Template End Time",
        "insert_after": "template_start_time"})
    _ensure_custom_field("PM Recurrence", {
        "fieldname": "template_duration_days", "fieldtype": "Int", "label": "Template Duration (days)",
        "default": "0", "insert_after": "template_end_time"})
    _ensure_custom_field("PM Recurrence", {
        "fieldname": "pm_checklist_items", "fieldtype": "Table", "label": "Checklist Items",
        "options": "PM Recurrence Checklist Item", "insert_after": "template_duration_days"})
    _ensure_custom_field("PM Recurrence", {
        "fieldname": "pm_subtasks", "fieldtype": "Table", "label": "Sub-tasks",
        "options": "PM Recurrence Subtask", "insert_after": "pm_checklist_items"})
    _ensure_custom_field("PM Recurrence", {
        "fieldname": "template_labels", "fieldtype": "Small Text", "label": "Template Labels (JSON)",
        "insert_after": "pm_subtasks"})

    # 4) source_task is no longer required (kept for audit/rollback; migrated by p018)
    _ensure_property_setter("PM Recurrence", "source_task", "reqd", "0", "Check")

    frappe.clear_cache()
