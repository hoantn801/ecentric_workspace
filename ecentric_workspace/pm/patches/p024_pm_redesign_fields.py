"""p024 - PM redesign (16/10/2026): new fields, idempotent + additive.

  Project.ec_personal_log      Check  - worklog project, hidden by default on every PM screen.
  Task.ec_auto_close           Check  - split parent closes itself when the last child is Done.
  Task.ec_review_required      Check  - a non-giver's Xong sends the task to Review.
  Task.ec_split_parent         Check  - parent created by "Mỗi người một việc" (roll-up target).
  PM Assignment Request.kind   Select Assignment/Deadline (default Assignment) - deadline
                                        requests ("Xin dời hạn") reuse the request doctype.

PM Assignment Request is an app-owned CUSTOM DocType created by p013 (no repo JSON), so `kind`
is added as a Custom Field like the p013 safety-net keys. Existing rows are backfilled to
'Assignment' so `kind` filters never meet NULL. Every step is wrapped: a failure is logged
(log_error), never raised, and re-running is a no-op.
"""

import frappe

_FIELDS = [
    ("Project", {"fieldname": "ec_personal_log", "fieldtype": "Check", "default": "0",
                 "label": "Nhật ký cá nhân (ẩn khỏi /pm)", "insert_after": "ec_manager",
                 "description": "Dự án worklog: mặc định ẩn ở mọi màn /pm và badge."}),
    ("Task", {"fieldname": "ec_auto_close", "fieldtype": "Check", "default": "0",
              "label": "Tự đóng khi mọi người xong", "insert_after": "priority"}),
    ("Task", {"fieldname": "ec_review_required", "fieldtype": "Check", "default": "0",
              "label": "Cần người giao kiểm tra", "insert_after": "ec_auto_close"}),
    ("Task", {"fieldname": "ec_split_parent", "fieldtype": "Check", "default": "0",
              "label": "Việc chung (mỗi người một việc)", "insert_after": "ec_review_required",
              "read_only": 1}),
    ("PM Assignment Request", {"fieldname": "kind", "fieldtype": "Select",
                               "options": "Assignment\nDeadline", "default": "Assignment",
                               "label": "Loại", "insert_after": "status", "in_list_view": 1,
                               "read_only": 1}),
]


def _ensure_custom_field(dt, df):
    if not frappe.db.exists("DocType", dt):
        frappe.log_error("p024: DocType %s not found; skipped %s" % (dt, df["fieldname"]),
                         "p024 PM redesign fields")
        return
    frappe.clear_cache(doctype=dt)
    if frappe.get_meta(dt, cached=False).has_field(df["fieldname"]):
        return
    payload = {"doctype": "Custom Field", "dt": dt}
    payload.update(df)
    frappe.get_doc(payload).insert(ignore_permissions=True)


def _backfill_kind():
    frappe.db.sql("""update `tabPM Assignment Request` set kind = 'Assignment'
                     where ifnull(kind, '') = ''""")


def execute():
    for dt, df in _FIELDS:
        try:
            _ensure_custom_field(dt, df)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "p024 field %s.%s" % (dt, df["fieldname"]))
    try:
        _backfill_kind()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p024 backfill kind")
    frappe.clear_cache()
