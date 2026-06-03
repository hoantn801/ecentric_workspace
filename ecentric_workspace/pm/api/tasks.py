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
from frappe.model.workflow import apply_workflow, get_transitions as _wf_get_transitions

from ecentric_workspace.pm import permissions as pmperm
from ecentric_workspace.pm.api import notifications as pmnotif

_FIELDS = [
    "name", "subject", "status", "workflow_state", "project", "parent_task", "is_group",
    "exp_start_date", "exp_end_date", "priority", "_assign", "owner", "modified",
]

# Fields a client may edit via tasks.update (whitelist -> no arbitrary injection).
_EDITABLE = ("subject", "description", "priority", "exp_start_date", "exp_end_date", "project")


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
        fields=["name", "subject", "status", "workflow_state", "_assign", "exp_end_date"],
        order_by="creation asc",
    )
    return {"task": doc.as_dict(), "subtasks": subtasks}


@frappe.whitelist()
def gantt(project):
    """Gantt data for ONE project (permission-scoped). Never loads all tasks.

    Returns rows with id/name/subject/project/start/end/progress/workflow_state/
    parent_task/dependencies. Dependencies use native Task Depends On if present,
    else an empty list (no custom field invented).
    """
    pmperm.require_pm_access()
    user = frappe.session.user
    if not project:
        frappe.throw(_("Project is required for the Gantt view."))
    if not pmperm.can_view_project(project, user):
        frappe.throw(_("Not permitted to view this project."), frappe.PermissionError)

    tasks = frappe.get_all(
        "Task", filters={"project": project},
        fields=["name", "subject", "project", "exp_start_date", "exp_end_date",
                "progress", "workflow_state", "parent_task"],
        order_by="exp_start_date asc, creation asc",
    )
    task_names = [t["name"] for t in tasks]

    deps = {}
    if task_names:
        try:
            for d in frappe.get_all("Task Depends On",
                                    filters={"parent": ["in", task_names]},
                                    fields=["parent", "task"]):
                deps.setdefault(d["parent"], []).append(d["task"])
        except Exception:
            deps = {}  # native depends_on table absent -> no dependencies

    rows = []
    for t in tasks:
        rows.append({
            "id": t["name"],
            "name": t["name"],
            "subject": t["subject"],
            "project": t["project"],
            "start": t.get("exp_start_date"),
            "end": t.get("exp_end_date"),
            "progress": t.get("progress") or 0,
            "workflow_state": t.get("workflow_state"),
            "parent_task": t.get("parent_task"),
            "dependencies": deps.get(t["name"], []),
        })
    return {"project": project, "rows": rows}


# --------------------------------------------------------------------------
# WRITE (PM1-T06) - permission validated in service layer; DocPerm + audit apply
# --------------------------------------------------------------------------
@frappe.whitelist()
def create(project, subject, parent_task=None, priority=None,
           exp_start_date=None, exp_end_date=None, description=None, assignee=None):
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
    if assignee:
        try:
            _assign_add({"doctype": "Task", "name": doc.name, "assign_to": [assignee]})
            pmnotif.notify_users([assignee], "Ban duoc giao nhiem vu: " + (doc.subject or doc.name), doc.name)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "PM create assign")
    return {"name": doc.name, "subject": doc.subject,
            "project": doc.project, "parent_task": doc.parent_task}


@frappe.whitelist()
def update(name, subject=None, description=None, priority=None,
           exp_start_date=None, exp_end_date=None, project=None, assignee=None):
    """Update whitelisted Task fields + optional assignee. Status -> set_status."""
    pmperm.require_pm_access()
    user = frappe.session.user
    doc = frappe.get_doc("Task", name)
    if not pmperm.can_view_task(doc.as_dict(), user):
        frappe.throw(_("Not permitted to edit this task."), frappe.PermissionError)

    incoming = {
        "subject": subject, "description": description, "priority": priority,
        "exp_start_date": exp_start_date, "exp_end_date": exp_end_date,
        "project": project,
    }
    changed = []
    for field in _EDITABLE:
        val = incoming.get(field)
        if val is not None:
            doc.set(field, val)
            changed.append(field)
    if changed:
        doc.save()  # honors DocPerm 'write'; audit trail

    if assignee:
        try:
            current = frappe.parse_json(doc.get("_assign") or "[]") or []
        except Exception:
            current = []
        if assignee not in current:
            try:
                _assign_add({"doctype": "Task", "name": doc.name, "assign_to": [assignee]})
                pmnotif.notify_users([assignee], "Ban duoc giao nhiem vu: " + (doc.subject or doc.name), doc.name)
                changed.append("assignee")
            except Exception:
                frappe.log_error(frappe.get_traceback(), "PM update assign")

    if not changed:
        frappe.throw(_("No changes provided."))
    return {"name": doc.name, "changed": changed}


@frappe.whitelist()
def assign(name, users):
    """Assign user(s) to a Task via NATIVE assignment (creates ToDo + _assign)."""
    pmperm.require_pm_access()
    user = frappe.session.user
    doc = frappe.get_doc("Task", name)
    if not pmperm.can_view_task(doc.as_dict(), user):
        frappe.throw(_("Not permitted to assign this task."), frappe.PermissionError)

    # NOTE: builtin `list` is shadowed by the read service `def list` in this
    # module, so do NOT reference the `list` type here. Parse via str checks only.
    if isinstance(users, str):
        try:
            users = json.loads(users)
        except Exception:
            users = [users]
    if isinstance(users, str):  # JSON decoded to a bare string (single email)
        users = [users]
    users = [u for u in (users or []) if u]
    if not users:
        frappe.throw(_("No users to assign."))

    _assign_add({"doctype": "Task", "name": name, "assign_to": users})
    pmnotif.notify_users(users, "Ban duoc giao nhiem vu: " + (doc.get("subject") or name), name)
    return {"name": name, "assigned": users,
            "_assign": frappe.db.get_value("Task", name, "_assign")}


@frappe.whitelist()
def get_transitions(name):
    """Allowed PM Task Workflow actions for the current user + task state (UI buttons)."""
    pmperm.require_pm_access()
    user = frappe.session.user
    doc = frappe.get_doc("Task", name)
    if not pmperm.can_view_task(doc.as_dict(), user):
        frappe.throw(_("Not permitted."), frappe.PermissionError)
    trans = _wf_get_transitions(doc)
    return {
        "current": doc.get("workflow_state"),
        "transitions": [{"action": t.get("action"), "next_state": t.get("next_state")} for t in trans],
    }


@frappe.whitelist()
def set_status(name, action):
    """Apply a PM Task Workflow transition by ACTION name (governed + audited).

    PM1-T07: replaces direct status writes. apply_workflow validates the
    transition is legal for the current workflow_state AND allowed for the
    user's role, and records the change in the document's audit trail.
    """
    pmperm.require_pm_access()
    user = frappe.session.user
    doc = frappe.get_doc("Task", name)
    if not pmperm.can_view_task(doc.as_dict(), user):
        frappe.throw(_("Not permitted to change this task."), frappe.PermissionError)
    doc = apply_workflow(doc, action)
    pmnotif.notify_users(pmnotif._task_recipients(doc.as_dict(), exclude=user),
                         "Nhiem vu '" + (doc.get("subject") or name) + "' -> " + (doc.get("workflow_state") or ""), name)
    return {"name": doc.name, "workflow_state": doc.get("workflow_state")}
