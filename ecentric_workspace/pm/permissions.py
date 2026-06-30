"""PM v2 - department-based permission model (PM1-T03, revised).

ENFORCED IN THE PM SERVICE LAYER ONLY (ecentric_workspace.pm.api.*). Global
`permission_query_conditions` on native Project/Task are intentionally NOT
registered, to avoid affecting other modules (GBS, Approval, Project dropdowns,
reports). Global hooks may be reconsidered after UAT.

Two separate concerns:
  * ROLE layer  -> capability / access to the PM module.
        PM Manager, PM Member (or System Manager / Administrator) may use PM.
        Checked by require_pm_access() in services; DocPerm covers Desk for
        PM Manager (desk_access=1).
  * DEPARTMENT layer -> data SCOPE (this module).

Scope rules:
  1. Administrator / System Manager        -> all PM data.
  2. User in Department `Management`        -> all PM data.
  3. Other users                           -> Project/Task whose
        Project.ec_department is one of the user's departments, PLUS anything
        they own, manage (Project.ec_manager), are a member of (Project User),
        or are assigned (_assign) -- even cross-department.

Department source: Employee.user_id -> Employee.department (primary).
`Employee Department Membership` is an OPTIONAL fallback only (fail-safe; never a
hard dependency, never raises).

No hardcoded users/emails: identity comes from frappe.session.user /
frappe.get_roles only.
"""

import frappe
from frappe import _

MANAGEMENT_DEPARTMENT = "Management"
PM_ROLES = ("PM Manager", "PM Member")


def _roles(user):
    return frappe.get_roles(user)


def has_pm_module_access(user=None):
    user = user or frappe.session.user
    if user == "Administrator":
        return True
    roles = _roles(user)
    if "System Manager" in roles:
        return True
    return any(r in roles for r in PM_ROLES)


def require_pm_access(user=None):
    """Capability guard for whitelisted PM services."""
    if not has_pm_module_access(user):
        frappe.throw(_("You do not have access to the PM module."), frappe.PermissionError)


def get_user_departments(user=None):
    """Primary: Employee.department. Optional fallback: Employee Department
    Membership. Fail-safe -> returns [] if unresolved, never raises."""
    user = user or frappe.session.user
    depts = set()
    try:
        emp = frappe.db.get_value(
            "Employee", {"user_id": user}, ["name", "department"], as_dict=True
        )
    except Exception:
        emp = None
    if emp:
        if emp.get("department"):
            depts.add(emp["department"])
        try:
            rows = frappe.get_all(
                "Employee Department Membership",
                filters={"parent": emp["name"]},
                fields=["department"],
            )
            for r in rows:
                if r.get("department"):
                    depts.add(r["department"])
        except Exception:
            pass  # optional fallback only
    return list(depts)


def can_see_all_pm_data(user=None):
    user = user or frappe.session.user
    if user == "Administrator":
        return True
    if "System Manager" in _roles(user):
        return True
    return MANAGEMENT_DEPARTMENT in get_user_departments(user)


def get_visible_project_names(user=None):
    """Names of Projects the user may see, or None = ALL (no restriction).

    Services use this to scope queries. Uses frappe.get_all (no user-perm
    filtering) so the service layer is the single trust boundary."""
    user = user or frappe.session.user
    if can_see_all_pm_data(user):
        return None
    names = set()
    depts = get_user_departments(user)
    if depts:
        for p in frappe.get_all("Project", filters={"ec_department": ["in", depts]},
                                fields=["name"]):
            names.add(p["name"])
    for p in frappe.get_all("Project", or_filters={"owner": user, "ec_manager": user},
                            fields=["name"]):
        names.add(p["name"])
    for r in frappe.get_all("Project User", filters={"user": user}, fields=["parent"]):
        names.add(r["parent"])
    return list(names)


def can_view_project(name, user=None):
    user = user or frappe.session.user
    visible = get_visible_project_names(user)
    if visible is None:
        return True
    return name in set(visible)


def can_view_task(task, user=None):
    """task: dict-like with keys name, owner, project, _assign."""
    user = user or frappe.session.user
    if can_see_all_pm_data(user):
        return True
    if task.get("owner") == user:
        return True
    if user in (task.get("_assign") or ""):
        return True
    project = task.get("project")
    if project and can_view_project(project, user):
        return True
    return False


def is_task_assignee(task, user=None):
    """G4.10: True if `user` is in the task's native _assign list. `task` is a dict/doc
    exposing _assign (same shape can_view_task consumes). Canonical assignee check."""
    user = user or frappe.session.user
    return user in (task.get("_assign") or "")


def can_transition_any_task(user=None):
    """G4.10: who may run ANY workflow transition (incl administrative Cancel) on any visible
    task. = PM leaders (can_see_all_pm_data: Administrator / System Manager / Management dept)
    OR the PM Manager role. PM Member is restricted to operational transitions on their own
    assigned tasks (enforced in the service layer + a Task before_save guard)."""
    user = user or frappe.session.user
    if can_see_all_pm_data(user):
        return True
    return "PM Manager" in _roles(user)


def can_request_task_assignment(task, user=None):
    """G5.0: who may delegate a task via an assignment request. = a PM leader
    (can_see_all_pm_data / Administrator / System Manager / Management dept), the PM Manager
    role, the task owner/creator, OR the linked Project's ec_manager. A read-only viewer or an
    ordinary assignee may NOT delegate merely because they can view the task. `task` is a
    dict/doc exposing owner + project."""
    user = user or frappe.session.user
    if can_see_all_pm_data(user):
        return True
    if "PM Manager" in _roles(user):
        return True
    if task.get("owner") == user:
        return True
    project = task.get("project")
    if project and frappe.db.get_value("Project", project, "ec_manager") == user:
        return True
    return False


def can_manage_pm_labels(user=None):
    """G4.9: who may manage the shared label catalogue (create / rename / recolor / archive).
    = PM leaders (can_see_all_pm_data: Administrator / System Manager / Management dept) OR the
    PM Manager role. PM Member may only attach/detach EXISTING ACTIVE labels (not manage the
    catalogue)."""
    user = user or frappe.session.user
    if can_see_all_pm_data(user):
        return True
    return "PM Manager" in _roles(user)


def task_scope_or_filters(user=None):
    """OR-filters for Task list scoping, or None = ALL.

    Combine with AND filters in frappe.get_all(filters=..., or_filters=...)."""
    user = user or frappe.session.user
    if can_see_all_pm_data(user):
        return None
    visible = get_visible_project_names(user) or []
    ors = [["owner", "=", user], ["_assign", "like", "%{0}%".format(user)]]
    if visible:
        ors.append(["project", "in", visible])
    return ors


# --------------------------------------------------------------------------
# Terminal-state helper (G4.3)
#
# Shared rule so timer/log/assign/checklist don't each re-implement the
# "is this task closed?" check. This is a PURE read predicate: it does NOT
# change any of the ROLE / DEPARTMENT permission logic above. Callers still
# run require_pm_access() + can_view_task() first; the terminal check is an
# ADDITIONAL operational guard layered on top.
#
# Terminal when:
#   workflow_state in (Done, Cancelled)              [canonical gate]
#   OR status in (Completed, Cancelled, Closed)      [belt-and-suspenders]
# --------------------------------------------------------------------------
TERMINAL_WORKFLOW_STATES = ("Done", "Cancelled")
TERMINAL_STATUSES = ("Completed", "Cancelled", "Closed")


def is_task_terminal(task):
    """True if a Task is in a terminal (closed) state.

    `task` may be a Frappe doc OR a plain dict (both expose .get)."""
    get = task.get if hasattr(task, "get") else (lambda k: getattr(task, k, None))
    return get("workflow_state") in TERMINAL_WORKFLOW_STATES or get("status") in TERMINAL_STATUSES


def assert_task_not_terminal(task, message=None):
    """Throw if the task is terminal. Reopen is the governed path to act again."""
    if is_task_terminal(task):
        frappe.throw(message or _("Nhiệm vụ đã hoàn thành/huỷ — vui lòng Reopen trước."))


def has_open_children(parent_name):
    """G4.8 (canonical, shared): True if a task has any DIRECT child task that is NOT
    terminal — reusing is_task_terminal (workflow_state Done/Cancelled OR status
    Completed/Cancelled/Closed). Single source of truth for the child-completion guard."""
    kids = frappe.get_all(
        "Task", filters={"parent_task": parent_name},
        fields=["name", "workflow_state", "status"], limit_page_length=0,
    )
    return any(not is_task_terminal(k) for k in kids)
