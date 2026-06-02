"""PM v2 - Task services (PM1-T05 read; write stubs reserved for PM1-T06).

Permission enforced in this service layer via ecentric_workspace.pm.permissions
(department-based scope). Hierarchy: Project -> Task -> Sub-task (parent_task).

Module path: ecentric_workspace.pm.api.tasks
"""

import frappe

from ecentric_workspace.pm import permissions as pmperm

_FIELDS = [
    "name", "subject", "status", "project", "parent_task", "is_group",
    "exp_start_date", "exp_end_date", "priority", "_assign", "owner", "modified",
]


@frappe.whitelist()
def list(project=None, view="list", start=0, page_length=50, status=None):
    """Permission-scoped task list.

    If `project` is given, returns its tasks (after checking the project is
    visible). Otherwise returns the user's in-scope tasks (own / assigned /
    in a visible project). Returns {rows, view}.
    """
    pmperm.require_pm_access()
    user = frappe.session.user

    and_filters = {}
    if status:
        and_filters["status"] = status

    or_filters = None
    if project:
        if not pmperm.can_view_project(project, user):
            frappe.throw(frappe._("Not permitted to view this project."), frappe.PermissionError)
        and_filters["project"] = project
    else:
        or_filters = pmperm.task_scope_or_filters(user)  # None = all
        if or_filters == []:
            return {"rows": [], "view": view}

    rows = frappe.get_all(
        "Task", filters=and_filters or None, or_filters=or_filters, fields=_FIELDS,
        start=int(start), page_length=int(page_length), order_by="modified desc",
    )
    return {"rows": rows, "view": view}


@frappe.whitelist()
def get(name):
    """Task detail + sub-tasks. Permission-checked."""
    pmperm.require_pm_access()
    user = frappe.session.user
    doc = frappe.get_doc("Task", name)
    if not pmperm.can_view_task(doc.as_dict(), user):
        frappe.throw(frappe._("Not permitted to view this task."), frappe.PermissionError)

    subtasks = frappe.get_all(
        "Task", filters={"parent_task": name},
        fields=["name", "subject", "status", "_assign", "exp_end_date"],
        order_by="creation asc",
    )
    return {"task": doc.as_dict(), "subtasks": subtasks}


# --- write services (PM1-T06) - stubs, not implemented yet ---

@frappe.whitelist()
def create(project=None, subject=None, parent_task=None):
    """Stub for PM1-T06. No write yet."""
    return {"ok": True, "service": "tasks.create", "implemented": False}


@frappe.whitelist()
def set_status(name=None, action=None):
    """Stub for PM1-T06/T07 (apply_workflow). No write yet."""
    return {"ok": True, "service": "tasks.set_status", "implemented": False}


@frappe.whitelist()
def assign(name=None, users=None):
    """Stub for PM1-T06 (native assign_to / ToDo). No write yet."""
    return {"ok": True, "service": "tasks.assign", "implemented": False}
