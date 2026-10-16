"""p026 - PM redesign (16/10/2026): mark existing "Mỗi người một việc" parents.

tasks.create(split_per_assignee=1) names every child "<parent subject[:120]> — <person>", and
from now on also sets Task.ec_split_parent = 1 on the parent. This backfills parents created
before that: a top-level group task whose children ALL carry that exact prefix. Only sets the
flag (no state change). Idempotent; failures logged, never raised.
"""

import frappe

SEP = " — "


def _is_split(parent, kids):
    if not kids:
        return False
    prefix = (parent.get("subject") or "")[:120] + SEP
    return all((k.get("subject") or "").startswith(prefix) for k in kids)


def execute():
    try:
        frappe.clear_cache(doctype="Task")
        if not frappe.get_meta("Task", cached=False).has_field("ec_split_parent"):
            frappe.log_error("p026: Task.ec_split_parent missing (p024 not applied)", "p026 split")
            return
        parents = frappe.get_all("Task", filters={"is_group": 1, "ec_split_parent": 0},
                                 fields=["name", "subject", "parent_task"], limit_page_length=0)
        marked = []
        for p in parents:
            if p.get("parent_task"):
                continue
            kids = frappe.get_all("Task", filters={"parent_task": p["name"]},
                                  fields=["subject"], limit_page_length=0)
            if _is_split(p, kids):
                frappe.db.set_value("Task", p["name"], "ec_split_parent", 1, update_modified=False)
                marked.append(p["name"])
        print("[p026] ec_split_parent=1 on %d task(s)" % len(marked))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p026 split parent backfill")
