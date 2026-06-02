"""PM v2 - Task services (PM1-T05 read + PM1-T06 write).

Permission enforced in this service layer via ecentric_workspace.pm.permissions
(department-based scope) + capability via require_pm_access(). Writes go through
normal frappe doc APIs so DocPerm (PM1-T03 p001) + audit trail apply.

Hierarchy (Phase 1): Project -> Task -> Sub-task (native parent_task).
Module path: ecentric_workspace.pm.api.tasks
"""

import json

import frappe
from frappe import _
from frappe.desk.form.assign_to import add as _assign_add

from ecentric_workspace.pm import permissions as pmperm

_FIELDS = [
    "name", "subject", "status", "project", "parent_task", "is_group",
    "exp_start_date", "exp_end_date", "priority", "_assign", "owner", "modified",
]

# Fields a client may edit via tasks.update (whitelist -> no arbitrary injection).
_EDITABLE = ("subject", "description", "priority", "exp_start_date", "exp_end_date")


# --------------------------------------------------------------------------
# READ (PM1-T05)
# --------------------------------------------------------------------------
@frappe.whitelist()
def list(project=None, view="list", start=0, page_length=50, status=None):
    """Permission-scoped task list. Returns {rows, view}."""
    pmperm.require_pm_access()
    user = frappe.session.user

    and_filters = {}
    if status:
        and_filters["status"] = status

    or_filters = None
    if project:
        if not pmperm.can_view_project(project, user):
            frappe.throw(_("Not permitted to view this project."), frappe.PermissionError)
        and_filters["project"] = project
    else:
        or_filters = pmperm.task_scope_or_filters(user)  # None = all

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
        frappe.throw(_("Not permitted to view this task."), frappe.PermissionError)
    subtasks = frappe.get_all(
        "Task", filters={"parent_task": name},
        fields=["name", "subject", "status", "_assign", "exp_end_date"],
        order_by="creation asc",
    )
    return {"task": doc.as_dict(), "subtasks": subtasks}


# --------------------------------------------------------------------------
# WRITE (PM1-T06) - permission validated in service layer; DocPerm + audit apply
# --------------------------------------------------------------------------
@frappe.whitelist()
def create(project, subject, parent_task=None, priority=None,
           exp_start_date=None, exp_end_date=None, description=None):
    """Create a Task (or sub-task via parent_task) under a project the user may see."""
    pmperm.require_pm_access()
    user = frappe.session.user
    if not project:
        frappe.throw(_("Project is required."))
    if not subject:
        frappe.throw(_("Subject is required."))
    if not pmperm.can_view_project(project, user):
        frappe.throw(_("Not permitted to create a task in this project."), frappe.PermissionError)
    if parent_task:
        pt = frappe.db.get_value("Task", parent_task, ["project"], as_dict=True)
        if not pt or pt.get("project") != project:
            frappe.throw(_("Parent task must belong to the same project."))

    doc = frappe.get_doc({
        "doctype": "Task",
        "subject": subject,
        "project": project,
        "parent_task": parent_task,
        "priority": priority,
        "exp_start_date": exp_start_date,
        "exp_end_date": exp_end_date,
        "description": description,
    })
    doc.insert()  # honors DocPerm 'create'; sets owner/creation (audit)
    return {"name": doc.name, "subject": doc.subject,
            "project": doc.project, "parent_task": doc.parent_task}


@frappe.whitelist()
def update(name, subject=None, description=None, priority=None,
           exp_start_date=None, exp_end_date=None):
    """Update whitelisted Task fields. Status changes go through set_status."""
    pmperm.require_pm_access()
    user = frappe.session.user
    doc = frappe.get_doc("Task", name)
    if not pmperm.can_view_task(doc.as_dict(), user):
        frappe.throw(_("Not permitted to edit this task."), frappe.PermissionError)

    incoming = {
        "subject": subject, "description": description, "priority": priority,
        "exp_start_date": exp_start_date, "exp_end_date": exp_end_date,
    }
    changed = []
    for field in _EDITABLE:
        val = incoming.get(field)
        if val is not None:
            doc.set(field, val)
            changed.append(field)
    if not changed:
        frappe.throw(_("No editable fields provided."))
    doc.save()  # honors DocPerm 'write'; audit trail
    return {"name": doc.name, "changed": changed}


@frappe.whitelist()
def assign(name, users):
    """Assign user(s) to a Task via NATIVE assignment (creates ToDo + _assign)."""
    pmperm.require_pm_access()
    user = frappe.session.user
    doc = frappe.get_doc("Task", name)
    if not pmperm.can_view_task(doc.as_dict(), user):
        frappe.throw(_("Not permitted to assign this task."), frappe.PermissionError)

    if isinstance(users, str):
        try:
            users = json.loads(users)
        except Exception:
            users = [users]
    if not isinstance(users, list):
        users = [users]
    users = [u for u in users if u]
    if not users:
        frappe.throw(_("No users to assign."))

    _assign_add({"doctype": "Task", "name": name, "assign_to": users})
    return {"name": name, "assigned": users,
            "_assign": frappe.db.get_value("Task", name, "_assign")}


@frappe.whitelist()
def set_status(name, status):
    """Set Task status (validated against Task.status options).

    INTERIM: direct status write with permission + audit. PM1-T07 will route this
    through the Task Workflow (apply_workflow) for governed transitions.
    """
    pmperm.require_pm_access()
    user = frappe.session.user
    doc = frappe.get_doc("Task", name)
    if not pmperm.can_view_task(doc.as_dict(), user):
        frappe.throw(_("Not permitted to change this task."), frappe.PermissionError)

    options = [o for o in (frappe.get_meta("Task").get_field("status").options or "").split("\n") if o]
    if options and status not in options:
        frappe.throw(_("Invalid status: {0}").format(status))
    doc.status = status
    doc.save()  # honors DocPerm 'write'; audit trail
    return {"name": doc.name, "status": doc.status}
