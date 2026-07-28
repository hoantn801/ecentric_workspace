# Copyright (c) 2026, eCentric and contributors
"""PM Task <-> ToDo lifecycle (Action Center Phase 1a).

Kept in its own light module (frappe + pmperm only, no assign_to/workflow
imports) so it loads and unit-tests without the full PM API surface. Wired
via the Task `on_update` doc_event in hooks.py."""
import frappe

from ecentric_workspace.pm import permissions as pmperm


def pm_task_close_todos_on_terminal(doc, method=None):
    """When a Task ENTERS a terminal state (workflow_state Done/Cancelled or
    native status Completed/Cancelled/Closed) on THIS save, cancel its Open
    assignment ToDos so the work leaves every user's Action feed.

    Runs on EVERY save path (API set_status + generic apply_workflow).
    Idempotent + narrowly scoped: fires only on the terminal TRANSITION (not
    on repeated saves of an already-terminal task), cancels ONLY Open ToDos
    of THIS task, uses ignore_permissions (a ToDo status flip never needs the
    actor to hold write/share on the Task -- mirrors the Approval engine's
    close_todos). The provider-side terminal filter is the correctness
    guarantee; this keeps tabToDo hygienic."""
    if frappe.flags.in_install or frappe.flags.in_migrate or frappe.flags.in_patch:
        return
    if not pmperm.is_task_terminal(doc):
        return
    before = doc.get_doc_before_save()
    if before is not None and pmperm.is_task_terminal(before):
        return  # already terminal before this save -> not a transition
    close_open_task_todos(doc.name)


def close_open_task_todos(task_name):
    """Cancel all Open ToDos referencing a Task. Governed, idempotent."""
    open_todos = frappe.get_all(
        "ToDo",
        filters={"reference_type": "Task", "reference_name": task_name, "status": "Open"},
        fields=["name"])
    for td in open_todos:
        frappe.db.set_value("ToDo", td["name"], "status", "Cancelled", update_modified=False)
    return len(open_todos)
