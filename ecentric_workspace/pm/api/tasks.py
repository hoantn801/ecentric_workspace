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

# G4.8: actions on the PM Task Workflow that land a task in "Done".
# Child-completion guard uses pmperm.has_open_children (canonical terminal semantics, shared).
_DONE_ACTIONS = ("Mark Done", "Hoàn thành")


def _names_map(emails):
    """email -> full_name (batch, avoids N+1). Falls back to the email when no full_name."""
    emails = [e for e in (emails or []) if e]
    if not emails:
        return {}
    out = {}
    for u in frappe.get_all("User", filters={"name": ["in", list(set(emails))]},
                            fields=["name", "full_name"]):
        out[u["name"]] = u.get("full_name") or u["name"]
    return out


def _collect_assignees(rows):
    out = []
    for r in rows:
        try:
            out += frappe.parse_json(r.get("_assign") or "[]") or []
        except Exception:
            pass
    return out


def _project_names(rows):
    pnames = [r.get("project") for r in rows if r.get("project")]
    if not pnames:
        return {}
    out = {}
    for p in frappe.get_all("Project", filters={"name": ["in", list(set(pnames))]},
                            fields=["name", "project_name"]):
        out[p["name"]] = p.get("project_name") or p["name"]
    return out


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
    # G4.8 additive: resolve project_name per row + a {email: full_name} map (batch, no N+1).
    pmap = _project_names(rows)
    for r in rows:
        r["project_name"] = pmap.get(r.get("project")) or (r.get("project") or None)
    return {"rows": rows, "view": view, "user_names": _names_map(_collect_assignees(rows))}


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
        fields=["name", "subject", "status", "workflow_state", "_assign",
                "exp_end_date", "priority"],
        order_by="creation asc",
    )
    d = doc.as_dict()
    d["_assign"] = doc.get("_assign")  # as_dict() doesn't reliably surface the _assign column; needed so the modal shows assignees
    # G4.8 additive: project display name + assignee name map. Sub-tasks inherit the project.
    d["project_name"] = (frappe.db.get_value("Project", d.get("project"), "project_name")
                         or d.get("project")) if d.get("project") else None
    for s in subtasks:
        s["project_name"] = d["project_name"]
    emails = _collect_assignees([d] + subtasks)
    if d.get("owner"):
        emails.append(d.get("owner"))
    return {"task": d, "subtasks": subtasks, "user_names": _names_map(emails)}


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
                "progress", "workflow_state", "parent_task", "priority", "_assign"],
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
            "priority": t.get("priority"),
            "_assign": t.get("_assign"),
            "dependencies": deps.get(t["name"], []),
        })
    return {"project": project, "rows": rows}


@frappe.whitelist()
def gantt_all(project=None, assignee=None, status=None, priority=None, overdue=None):
    """All-project Gantt (UX-4E2). Permission-scoped via the service layer. If `project`
    is empty/'all', returns every task in the user's PM scope grouped client-side by
    project (each row carries project + project_name). Additive, no schema.
    """
    pmperm.require_pm_access()
    user = frappe.session.user
    today = frappe.utils.nowdate()

    and_filters = {}
    or_filters = None
    if project and project != "all":
        if not pmperm.can_view_project(project, user):
            frappe.throw(_("Not permitted to view this project."), frappe.PermissionError)
        and_filters["project"] = project
    else:
        or_filters = pmperm.task_scope_or_filters(user)  # None = all in PM
    if status:
        and_filters["workflow_state"] = status
    if priority:
        and_filters["priority"] = priority

    tasks = frappe.get_all(
        "Task", filters=and_filters or None, or_filters=or_filters,
        fields=["name", "subject", "project", "exp_start_date", "exp_end_date",
                "progress", "workflow_state", "parent_task", "priority", "_assign"],
        order_by="project asc, exp_start_date asc, creation asc", limit_page_length=0,
    )

    if assignee:
        tasks = [t for t in tasks
                 if assignee in (frappe.parse_json(t.get("_assign") or "[]") or [])]
    if overdue in (1, "1", True, "true", "True", "yes"):
        def _od(t):
            d = t.get("exp_end_date")
            d = str(d)[:10] if d else None
            return bool(d and d < today and t.get("workflow_state") not in ("Done", "Cancelled"))
        tasks = [t for t in tasks if _od(t)]

    # NOTE: this module defines `def list(...)`, which shadows the builtin `list`.
    # Calling bare list(...) here would invoke tasks.list() -> bad SQL. Use sorted().
    proj_ids = sorted({t["project"] for t in tasks if t.get("project")})
    pnames = {}
    if proj_ids:
        for r in frappe.get_all("Project", filters={"name": ["in", proj_ids]},
                                fields=["name", "project_name"]):
            pnames[r["name"]] = r.get("project_name")

    rows = []
    for t in tasks:
        rows.append({
            "id": t["name"], "name": t["name"], "subject": t["subject"],
            "project": t["project"], "project_name": pnames.get(t["project"]) or t["project"],
            "start": t.get("exp_start_date"), "end": t.get("exp_end_date"),
            "progress": t.get("progress") or 0, "workflow_state": t.get("workflow_state"),
            "parent_task": t.get("parent_task"), "priority": t.get("priority"),
            "_assign": t.get("_assign"),
        })
    return {"rows": rows}


# --------------------------------------------------------------------------
# WRITE (PM1-T06) - permission validated in service layer; DocPerm + audit apply
# --------------------------------------------------------------------------
def _expand_ancestor_dates(parent_task, child_start, child_end, user):
    """Widen the WHOLE ancestor chain (root -> direct parent) so it covers a child's
    date range. ERPNext validates a task's exp_end_date <= its parent's exp_end_date,
    so a nested subtask whose dates exceed an ancestor would be rejected. We expand the
    chain first.

    Safe by construction:
    - cycle/runaway guarded (visited-set + max depth);
    - permission pre-flight on every ancestor (atomic: throw before any write, and the
      request transaction rolls back any partial save on a later error);
    - saves TOP-DOWN (root first) so each doc.save() is individually valid against its
      own (already-widened) parent -> NO ignore_validate, NO flags, audit trail intact;
    - missing parent link / empty dates handled gracefully.
    Additive, no schema change.
    """
    if not parent_task or (not child_start and not child_end):
        return

    cs = frappe.utils.getdate(child_start) if child_start else None
    ce = frappe.utils.getdate(child_end) if child_end else None

    # 1. Walk direct-parent -> root, collecting ancestor docs (guarded).
    chain = []
    seen = set()
    cur = parent_task
    depth = 0
    while cur and cur not in seen and depth < 25:
        seen.add(cur)
        depth += 1
        try:
            anc = frappe.get_doc("Task", cur)
        except frappe.DoesNotExistError:
            break  # broken parent link -> stop gracefully
        chain.append(anc)
        cur = anc.get("parent_task")

    if not chain:
        return

    # 2. Permission pre-flight on every ancestor (same gate as other writes).
    for anc in chain:
        if not pmperm.can_view_task(anc.as_dict(), user):
            frappe.throw(
                _("Not permitted to adjust the date range of parent task {0}.").format(anc.name),
                frappe.PermissionError,
            )

    # 3. Save TOP-DOWN (root -> direct parent): when each ancestor is saved its own
    #    parent has already been widened, so ERPNext's parent-date check passes.
    for anc in reversed(chain):
        changed = False
        if cs is not None:
            anc_start = frappe.utils.getdate(anc.exp_start_date) if anc.get("exp_start_date") else None
            if anc_start is None or cs < anc_start:
                anc.exp_start_date = cs
                changed = True
        if ce is not None:
            anc_end = frappe.utils.getdate(anc.exp_end_date) if anc.get("exp_end_date") else None
            if anc_end is None or ce > anc_end:
                anc.exp_end_date = ce
                changed = True
        if changed:
            anc.save()  # normal validated save -> audit/history intact


def _expand_project_dates(project, child_start, child_end, user):
    """Widen the Project's expected date range so it covers a task/subtask's dates.
    ERPNext validates Task.exp_end_date <= Project.expected_end_date, so a task whose
    dates exceed the project would be rejected -- and so would any ancestor task save.
    MUST run BEFORE ancestor expansion (ancestor task saves are also project-validated).
    Permission via existing can_view_project; normal doc.save() -> validation + audit
    intact (no ignore_validate / flags). Additive, no schema.
    """
    if not project or (not child_start and not child_end):
        return
    cs = frappe.utils.getdate(child_start) if child_start else None
    ce = frappe.utils.getdate(child_end) if child_end else None
    try:
        proj = frappe.get_doc("Project", project)
    except frappe.DoesNotExistError:
        return  # missing project link -> stop gracefully
    if not pmperm.can_view_project(project, user):
        frappe.throw(
            _("Not permitted to adjust the date range of project {0}.").format(project),
            frappe.PermissionError,
        )
    changed = False
    if cs is not None:
        p_start = frappe.utils.getdate(proj.expected_start_date) if proj.get("expected_start_date") else None
        if p_start is None or cs < p_start:
            proj.expected_start_date = cs
            changed = True
    if ce is not None:
        p_end = frappe.utils.getdate(proj.expected_end_date) if proj.get("expected_end_date") else None
        if p_end is None or ce > p_end:
            proj.expected_end_date = ce
            changed = True
    if changed:
        proj.save()  # normal validated save -> audit/history intact


@frappe.whitelist()
def create(project, subject, parent_task=None, priority=None,
           exp_start_date=None, exp_end_date=None, description=None, assignee=None):
    """Create a Task (or sub-task via parent_task) under a project the user may see."""
    pmperm.require_pm_access()
    user = frappe.session.user
    if not subject:
        frappe.throw(_("Subject is required."))
    if parent_task:
        # ERPNext Task is a NestedSet tree: a parent can only hold children if it is a
        # Group Task (is_group=1). Ensure that before inserting the child, with the same
        # service-layer permission checks. No schema change (is_group is a native field).
        parent = frappe.get_doc("Task", parent_task)
        if not pmperm.can_view_task(parent.as_dict(), user):
            frappe.throw(_("Not permitted to add a sub-task to this task."), frappe.PermissionError)
        # G4.8: a sub-task ALWAYS inherits its parent's project (incl. empty = task ngoài dự án).
        if not project:
            project = parent.get("project")
        elif (parent.get("project") or None) != (project or None):
            frappe.throw(_("Parent task must belong to the same project."))
        if not parent.get("is_group"):
            parent.is_group = 1
            parent.save()  # honors DocPerm 'write' + audit; NestedSet handles the flag
    # G4.8: project is OPTIONAL (task ngoài dự án = empty project). When set, must be viewable.
    if project and not pmperm.can_view_project(project, user):
        frappe.throw(_("Not permitted to create a task in this project."), frappe.PermissionError)

    # Widen Project range FIRST (ERPNext validates task end <= project end), then the
    # whole ancestor task chain, before inserting the child.
    if project and (exp_start_date or exp_end_date):
        _expand_project_dates(project, exp_start_date, exp_end_date, user)
    if parent_task and (exp_start_date or exp_end_date):
        _expand_ancestor_dates(parent_task, exp_start_date, exp_end_date, user)

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
            # adopt-native task_assigned: snapshot the prior native log, do the native
            # assignment, then enqueue ONE post-commit delivery job (Frappe creates the
            # native Assignment log asynchronously).
            _assign_add({"doctype": "Task", "name": doc.name, "assign_to": [assignee]})
            pmnotif.notify_task_assignment([assignee], doc.name,
                                           "Ban duoc giao nhiem vu: " + (doc.subject or doc.name),
                                           actor=user)
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
    # G4.8: a sub-task must stay in its parent's project — block moving it to a different one.
    if project is not None and doc.get("parent_task"):
        parent_project = frappe.db.get_value("Task", doc.get("parent_task"), "project")
        if (parent_project or None) != (project or None):
            frappe.throw(_("Không thể đổi dự án của nhiệm vụ con khác với nhiệm vụ cha."))

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
    # If the task's dates moved, widen Project range FIRST then the ancestor chain (fixes
    # Gantt move/resize, drag-unscheduled, inline date edit, and any other date path).
    _date_changed = ("exp_start_date" in changed) or ("exp_end_date" in changed)
    if _date_changed and doc.get("project"):
        _expand_project_dates(doc.get("project"), doc.get("exp_start_date"), doc.get("exp_end_date"), user)
    if _date_changed and doc.get("parent_task"):
        _expand_ancestor_dates(doc.get("parent_task"), doc.get("exp_start_date"), doc.get("exp_end_date"), user)
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
                pmnotif.notify_task_assignment([assignee], doc.name,
                                               "Ban duoc giao nhiem vu: " + (doc.subject or doc.name),
                                               actor=user)
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
    # G4.3: cannot assign a terminal task. Reopen first.
    pmperm.assert_task_not_terminal(
        doc, _("Không thể giao nhiệm vụ đã hoàn thành/huỷ. Vui lòng Reopen trước."))

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
    pmnotif.notify_task_assignment(users, name,
                                   "Ban duoc giao nhiem vu: " + (doc.get("subject") or name),
                                   actor=user)
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
    # G4.8: cannot complete a parent while it still has open sub-tasks (canonical terminal check).
    if action in _DONE_ACTIONS and pmperm.has_open_children(name):
        frappe.throw(_("Không thể hoàn thành nhiệm vụ khi vẫn còn nhiệm vụ con chưa đóng."))
    doc = apply_workflow(doc, action)
    pmnotif.notify_users(pmnotif._task_recipients(doc.as_dict(), exclude=user),
                         "Nhiem vu '" + (doc.get("subject") or name) + "' -> " + (doc.get("workflow_state") or ""),
                         name, event_type="mention", severity="info",
                         due_suffix=doc.get("workflow_state"))
    return {"name": doc.name, "workflow_state": doc.get("workflow_state")}


@frappe.whitelist()
def delete(name):
    """Controlled hard-delete of a Task. LEADER-ONLY (can_see_all_pm_data). Allowed only
    when the task has NO dependents (authoritative server-side checks; never trusts the
    frontend): no child task, no Running/Paused PM Timer, no Timesheet Detail log. Uses
    the standard frappe.delete_doc (no SQL, no force, no manual cascade) so Frappe's own
    link checks still run; if any other document links the task, a clear error is returned.
    """
    pmperm.require_pm_access()
    user = frappe.session.user
    if not pmperm.can_see_all_pm_data(user):
        frappe.throw(_("Only PM leaders can delete tasks."), frappe.PermissionError)
    if not frappe.db.exists("Task", name):
        frappe.throw(_("Task not found."))
    if frappe.db.count("Task", {"parent_task": name}):
        frappe.throw(_("Nhiệm vụ có công việc con và không thể xoá."))
    if frappe.db.count("PM Timer", {"task": name, "status": ["in", ["Running", "Paused"]]}):
        frappe.throw(_("Nhiệm vụ đang có timer và không thể xoá."))
    if frappe.db.count("Timesheet Detail", {"task": name}):
        frappe.throw(_("Nhiệm vụ đã có log giờ và không thể xoá. Hãy huỷ nhiệm vụ thay vì xoá."))
    try:
        frappe.delete_doc("Task", name, ignore_permissions=True)  # service layer is the gate; no force -> link checks apply
    except frappe.LinkExistsError:
        frappe.throw(_("Không thể xoá: nhiệm vụ còn liên kết với dữ liệu khác. "
                       "Hãy gỡ liên kết hoặc huỷ nhiệm vụ."))
    return {"deleted": name}


@frappe.whitelist()
def subtree(name):
    """G4.8 additive: ALL descendant tasks (multi-level) under `name`, returned as a flat
    list carrying parent_task so the client builds the tree. No schema. Permission-checked
    on the root; descendants are within the same project scope as the root. BFS per level
    (one query per depth) to avoid N+1; a guard caps pathological depth."""
    pmperm.require_pm_access()
    user = frappe.session.user
    root = frappe.get_doc("Task", name)
    if not pmperm.can_view_task(root.as_dict(), user):
        frappe.throw(_("Not permitted to view this task."), frappe.PermissionError)
    out, frontier, seen, guard = [], [name], set(), 0
    while frontier and guard < 5000:
        guard += 1
        kids = frappe.get_all(
            "Task", filters={"parent_task": ["in", frontier]},
            fields=["name", "subject", "status", "workflow_state", "parent_task",
                    "_assign", "exp_end_date", "priority", "is_group"],
            order_by="creation asc", limit_page_length=0,
        )
        frontier = []
        for k in kids:
            if k["name"] in seen:
                continue
            seen.add(k["name"])
            out.append(k)
            frontier.append(k["name"])
    return {"rows": out, "user_names": _names_map(_collect_assignees(out))}
