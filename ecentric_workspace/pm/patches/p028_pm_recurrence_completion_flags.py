"""p028 - PM redesign (16/10/2026): completion flags on PM Recurrence, idempotent + additive.

  PM Recurrence.split_per_assignee  Check - each occurrence is a split parent ("Mỗi người một
                                            việc") with one child per template assignee.
  PM Recurrence.auto_close          Check - copied to Task.ec_auto_close on every occurrence.
  PM Recurrence.review_required     Check - copied to Task.ec_review_required on every occurrence.

Written by recurrence.create / update_template / create_from_task (which copies them from the
source task), applied by recurrence._clone. PM Recurrence is an app-owned custom DocType (p004),
so these are Custom Fields like p020's schedule fields. Default 0 = the previous behaviour for
every existing rule. Every step is wrapped: a failure is logged, never raised; re-run = no-op.
"""

import frappe

DT = "PM Recurrence"
_FIELDS = [
    {"fieldname": "split_per_assignee", "fieldtype": "Check", "default": "0",
     "label": "Mỗi người một việc", "insert_after": "monthly_day"},
    {"fieldname": "auto_close", "fieldtype": "Check", "default": "0",
     "label": "Tự đóng khi mọi người xong", "insert_after": "split_per_assignee"},
    {"fieldname": "review_required", "fieldtype": "Check", "default": "0",
     "label": "Cần người giao kiểm tra", "insert_after": "auto_close"},
]


def _ensure_custom_field(df):
    if frappe.db.exists("Custom Field", DT + "-" + df["fieldname"]):
        return
    frappe.clear_cache(doctype=DT)
    if frappe.get_meta(DT, cached=False).has_field(df["fieldname"]):
        return
    payload = {"doctype": "Custom Field", "dt": DT}
    payload.update(df)
    frappe.get_doc(payload).insert(ignore_permissions=True)


def execute():
    if not frappe.db.exists("DocType", DT):
        frappe.log_error("p028: DocType %s not found; skipped" % DT, "p028 PM recurrence flags")
        return
    for df in _FIELDS:
        try:
            _ensure_custom_field(df)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "p028 field %s.%s" % (DT, df["fieldname"]))
    frappe.clear_cache()
