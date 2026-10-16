"""p027 - PM redesign (16/10/2026): baseline for "chưa mở" (unopened).

PM Task Seen starts empty, so on day one every open assigned task would look "unopened" and
flood "Được giao cho tôi". Baseline: every assignee of every currently OPEN task is recorded as
having seen it (first_seen = last_seen = now). Only tasks assigned AFTER deploy can show as
unopened. Idempotent (natural key task::user, existing rows skipped); errors logged, not raised.
"""

import json

import frappe

DT = "PM Task Seen"


def execute():
    try:
        if not frappe.db.exists("DocType", DT):
            frappe.log_error("p027: DocType PM Task Seen missing", "p027 seen baseline")
            return
        now = frappe.utils.now_datetime()
        rows = frappe.get_all("Task", filters={"workflow_state": ["not in", ["Done", "Cancelled"]],
                                               "_assign": ["is", "set"]},
                              fields=["name", "_assign"], limit_page_length=0)
        made = 0
        for r in rows:
            try:
                users = json.loads(r.get("_assign") or "[]") or []
            except Exception:
                users = []
            for u in users:
                key = "{0}::{1}".format(r["name"], u)
                if not u or frappe.db.exists(DT, key):
                    continue
                try:
                    frappe.get_doc({"doctype": DT, "task": r["name"], "user": u,
                                    "first_seen": now, "last_seen": now}).insert(
                        ignore_permissions=True)
                    made += 1
                except Exception:
                    frappe.log_error(frappe.get_traceback(), "p027 seen %s" % key)
        print("[p027] PM Task Seen baseline rows: %d" % made)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p027 seen baseline")
