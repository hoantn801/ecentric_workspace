# Copyright (c) 2026, eCentric and contributors
"""p002_reconcile_stale_task_todos: one-time cleanup of Open ToDos whose
Task is ALREADY terminal (Done/Cancelled/Completed/Closed).

Context (Action Center Phase 1a): PM's terminal transition did not previously
close assignment ToDos, so a Task marked Done via workflow_state could leave
an Open ToDo behind -> the item lingered in the Action feed. Going forward
`pm_task_close_todos_on_terminal` closes them at transition time; this patch
reconciles the backlog that accumulated BEFORE that hook existed.

Deployment classification: DATA MIGRATION (patches.txt). NO schema change.
Idempotent: only touches ToDos that are Open AND reference a terminal Task;
re-running finds none. The provider-side terminal filter already HIDES these
rows, so this patch is hygiene, not correctness -- safe to run anytime.
"""
import frappe

from ecentric_workspace.pm import permissions as pmperm


def execute():
    if not frappe.db.table_exists("ToDo") or not frappe.db.exists("DocType", "Task"):
        return
    open_task_todos = frappe.get_all(
        "ToDo",
        filters={"reference_type": "Task", "status": "Open"},
        fields=["name", "reference_name"])
    if not open_task_todos:
        return
    task_names = sorted({t["reference_name"] for t in open_task_todos if t.get("reference_name")})
    tasks = frappe.get_all(
        "Task", filters={"name": ["in", task_names]},
        fields=["name", "workflow_state", "status"]) if task_names else []
    tstate = {t["name"]: t for t in tasks}
    closed = 0
    for td in open_task_todos:
        t = tstate.get(td.get("reference_name"))
        # missing Task OR terminal Task -> the assignment is resolved
        if t is None or pmperm.is_task_terminal(t):
            frappe.db.set_value("ToDo", td["name"], "status", "Cancelled", update_modified=False)
            closed += 1
    if closed:
        frappe.logger().info("p002_reconcile_stale_task_todos: closed %d stale Task ToDo(s)" % closed)
