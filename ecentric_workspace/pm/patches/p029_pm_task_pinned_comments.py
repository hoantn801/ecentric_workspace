"""p029 - PM hotfix 1 (16/10/2026): Task.ec_pinned_comments (hidden Small Text, JSON list of
Comment names) backing "Ghim bình luận" in /pm (pm.api.comments.pin). Additive + idempotent;
a failure is logged, never raised."""

import frappe

_DF = {"fieldname": "ec_pinned_comments", "fieldtype": "Small Text", "label": "Bình luận đã ghim",
       "insert_after": "ec_split_parent", "hidden": 1, "read_only": 1, "no_copy": 1,
       "description": "Danh sách bình luận được ghim trong /pm (JSON)."}


def execute():
    try:
        if not frappe.db.exists("DocType", "Task"):
            return
        frappe.clear_cache(doctype="Task")
        if frappe.get_meta("Task", cached=False).has_field(_DF["fieldname"]):
            return
        payload = {"doctype": "Custom Field", "dt": "Task"}
        payload.update(_DF)
        frappe.get_doc(payload).insert(ignore_permissions=True)
        frappe.clear_cache(doctype="Task")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p029 PM pinned comments field")
