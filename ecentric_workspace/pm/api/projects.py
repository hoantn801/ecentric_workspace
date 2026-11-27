"""PM v2 - Project read services (PM1-T05).

Permission enforced in this service layer via ecentric_workspace.pm.permissions
(department-based scope). No global permission_query_conditions are used.

Module path: ecentric_workspace.pm.api.projects
"""

import frappe
from frappe import _

from ecentric_workspace.pm import permissions as pmperm
from ecentric_workspace.pm import colors as pmcolors
from ecentric_workspace.pm import task_flow as tflow

_FIELDS = [
    "name", "project_name", "status", "percent_complete",
    "ec_department", "ec_manager", "owner", "modified", "_user_tags",
]

# Project.status values the PM screens use. "closed" = Completed + Cancelled (hotfix 23 scope).
PROJECT_STATUSES = ("Open", "Completed", "Cancelled")
CLOSED_STATUSES = ("Completed", "Cancelled")
SCOPES = ("run", "closed", "mine")
_FINISHED = ["Done", "Cancelled"]
_HEALTH = {"high": "hi", "medium": "mid", "low": "ok"}


def _fields():
    return _FIELDS + ([pmcolors.COLOR_FIELD] if pmcolors.has_color_field() else [])


# --------------------------------------------------------------------------- risk / health
def _task_assignees(t):
    return pmperm.assignees_of(t)


def risk_summary(rows, today):
    """Risk counters over a project's (scoped) task rows. SINGLE definition shared by
    projects.detail (risk / risk_level, unchanged since UX-3) and projects.list (health):
      high   if overdue > 0 or blocked > 0
      medium if (no_assignee + no_due) >= max(3, total // 2)
      low    otherwise.
    rows need workflow_state, exp_end_date, _assign. Returns (risk dict, level, total)."""
    def active(t):
        return t.get("workflow_state") not in _FINISHED

    def overdue(t):
        d = t.get("exp_end_date")
        d = str(d)[:10] if d else None
        return bool(d and d < today and active(t))

    total = len(rows)
    risk = {
        "active": len([t for t in rows if active(t)]),
        "overdue": len([t for t in rows if overdue(t)]),
        "blocked": len([t for t in rows if t.get("workflow_state") == "Blocked"]),
        "review": len([t for t in rows if t.get("workflow_state") == "Review"]),
        "no_assignee": len([t for t in rows if not _task_assignees(t)]),
        "no_due": len([t for t in rows if not t.get("exp_end_date")]),
        "completed": len([t for t in rows if t.get("workflow_state") == "Done"]),
    }
    if risk["overdue"] > 0 or risk["blocked"] > 0:
        level = "high"
    elif (risk["no_assignee"] + risk["no_due"]) >= max(3, total // 2):
        level = "medium"
    else:
        level = "low"
    return risk, level, total


def health_of(risk, level, total, status=None):
    """-> (health in hi|mid|ok|"", health_text). Same thresholds as risk_summary (the label the
    project detail header has shown as Rủi ro cao / Cần chú ý / Ổn định); "" when there is
    nothing to judge (no task yet, or the project is closed)."""
    if status in CLOSED_STATUSES:
        return "", (_("Dự án đã hoàn thành") if status == "Completed" else _("Dự án đã huỷ"))
    if not total:
        return "", _("Chưa có việc")
    h = _HEALTH.get(level, "ok")
    if h == "hi":
        parts = []
        if risk["overdue"]:
            parts.append(_("{0} việc quá hạn trên {1} việc đang mở").format(risk["overdue"], risk["active"]))
        if risk["blocked"]:
            parts.append(_("{0} việc đang bị chặn").format(risk["blocked"]))
        return h, " · ".join(parts)
    if h == "mid":
        return h, _("{0} việc chưa giao, {1} việc chưa có hạn trên {2} việc").format(
            risk["no_assignee"], risk["no_due"], total)
    return h, _("Không có việc quá hạn hay bị chặn ({0} việc đang mở)").format(risk["active"])


# --------------------------------------------------------------------------- manage gate
def can_manage_project(project_row, user=None, is_leader=None):
    """Who may edit / close / cancel / recolour / delete (0 tasks) a project: a PM leader
    (pmperm.can_see_all_pm_data) OR the project's ec_manager. Same rule as projects.update."""
    user = user or frappe.session.user
    if is_leader is None:
        is_leader = pmperm.can_see_all_pm_data(user)
    return bool(is_leader or ((project_row or {}).get("ec_manager") or None) == user)


def _managed_doc(name, action):
    """Load a project the caller may manage, else a Vietnamese error. `action` completes the
    sentence "Chỉ quản lý dự án hoặc trưởng nhóm PM mới ... được"."""
    pmperm.require_pm_access()
    if not name or not frappe.db.exists("Project", name):
        frappe.throw(_("Không tìm thấy dự án."))
    doc = frappe.get_doc("Project", name)
    if not can_manage_project(doc, frappe.session.user):
        frappe.throw(_("Chỉ quản lý dự án hoặc trưởng nhóm PM mới {0} được.").format(action),
                     frappe.PermissionError)
    return doc


# --------------------------------------------------------------------------- list
def _base_filters(user, include_personal, status, q):
    """List-form filters shared by rows / total / counts. None = the user can open nothing."""
    filters = []
    if status:
        filters.append(["status", "=", status])
    q = (q or "").strip()
    if q:
        esc = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        filters.append(["project_name", "like", "%{0}%".format(esc)])
    personal = tflow.personal_log_projects()
    hide = set() if tflow.truthy(include_personal) else personal
    visible = pmperm.get_visible_project_names(user)
    if visible is not None:
        # need-to-know: also show projects where the user only has an assigned/owned task
        # (they can open it, but its task list is scoped to their own tasks). NOTE: this module
        # defines `def list`, which shadows the builtin `list` -> use sorted(), never bare list().
        openable = (set(visible) | pmperm.projects_with_my_tasks(user)) - hide
        if not openable:
            return None, personal
        filters.append(["name", "in", sorted(openable)])
    elif hide:
        filters.append(["name", "not in", sorted(hide)])  # Project.name is never NULL
    return filters, personal


def _mine_names(filters, user):
    return frappe.get_all("Project", filters=filters,
                          or_filters=[["owner", "=", user], ["ec_manager", "=", user]],
                          pluck="name", limit_page_length=0)


def _scope_filter(scope, mine):
    if scope == "run":
        return [["status", "not in", sorted(CLOSED_STATUSES)]]
    if scope == "closed":
        return [["status", "in", sorted(CLOSED_STATUSES)]]
    if scope == "mine":
        return [["name", "in", sorted(mine)]]
    return []


def _decorate_rows(rows, user):
    """Task aggregates + health + colour + manage flags for one page of projects (one Task query,
    scoped to the user's own tasks like before)."""
    today = frappe.utils.nowdate()
    names = [r["name"] for r in rows]
    by = {}
    if names:
        for t in frappe.get_all(
            "Task", filters={"project": ["in", names]},
            or_filters=pmperm.task_scope_or_filters(user),  # scope counts to the user's own tasks
            fields=["project", "workflow_state", "exp_end_date", "_assign"], limit_page_length=0,
        ):
            by.setdefault(t["project"], []).append(t)
    is_leader = pmperm.can_see_all_pm_data(user)
    mgr_names = tflow.full_names([r.get("ec_manager") for r in rows])
    for r in rows:
        tl = by.get(r["name"], [])
        risk, level, total = risk_summary(tl, today)
        # Computed progress from task completion (native percent_complete is unreliable here
        # since PM uses workflow_state). Same definition as projects.detail: Done / total.
        r["task_total"] = total
        r["task_done"] = risk["completed"]
        r["progress"] = int(round(risk["completed"] * 100.0 / total)) if total else 0
        r["open"] = risk["active"]
        r["late"] = risk["overdue"]
        r["unassigned"] = len([t for t in tl if t.get("workflow_state") not in _FINISHED
                               and not _task_assignees(t)])
        r["health"], r["health_text"] = health_of(risk, level, total, r.get("status"))
        r["color_key"] = pmcolors.color_for(r)
        r["ec_manager_name"] = mgr_names.get(r.get("ec_manager")) if r.get("ec_manager") else None
        r["can_manage"] = can_manage_project(r, user, is_leader)
        # can_delete needs the AUTHORITATIVE count (the page count above is user-scoped).
        r["can_delete"] = bool(r["can_manage"] and not total)
    # can_delete needs the AUTHORITATIVE count; one grouped query for all candidates (QC 27/11, no N+1)
    cands = [r["name"] for r in rows if r.get("can_delete")]
    if cands:
        have = {x["project"] for x in frappe.get_all("Task", filters={"project": ["in", cands]},
                                                     fields=["project"], distinct=True, limit_page_length=0)}
        for r in rows:
            if r.get("can_delete") and r["name"] in have:
                r["can_delete"] = False
    return rows


@frappe.whitelist()
def list(start=0, page_length=20, status=None, include_personal=0, scope=None, q=None):
    """Permission-scoped, paginated project list.

    Returns {rows, total, counts: {run, closed, mine}}.
      scope  run (not Completed/Cancelled) | closed (Completed + Cancelled) | mine (I own or
             manage it) | None = every visible project (legacy callers: dropdowns, 200/500 rows).
      q      substring of project_name. `counts` follow q + include_personal, not scope.
    PM redesign: personal-log projects (ec_personal_log=1, the worklog) are hidden unless
    include_personal=1; every row carries ec_personal_log (0/1). Hotfix 23 row additions:
    open, late, unassigned, health (hi|mid|ok|""), health_text, color_key, ec_manager_name,
    can_manage, can_delete."""
    pmperm.require_pm_access()
    user = frappe.session.user
    scope = (scope or "").strip().lower() or None
    if scope and scope not in SCOPES:
        frappe.throw(_("Bộ lọc dự án không hợp lệ: {0}").format(scope))
    try:
        start = max(0, int(start or 0))
        page_length = 20 if page_length in (None, "") else max(0, int(page_length))  # 0 = all (legacy)
    except (TypeError, ValueError):
        frappe.throw(_("Tham số phân trang không hợp lệ."))

    base, personal = _base_filters(user, include_personal, status, q)
    if base is None:
        return {"rows": [], "total": 0, "counts": {"run": 0, "closed": 0, "mine": 0}}
    mine = _mine_names(base, user)
    counts = {"run": frappe.db.count("Project", base + _scope_filter("run", mine)),
              "closed": frappe.db.count("Project", base + _scope_filter("closed", mine)),
              "mine": len(mine)}
    if scope == "mine" and not mine:
        return {"rows": [], "total": 0, "counts": counts}
    filters = base + _scope_filter(scope, mine)

    rows = frappe.get_all(
        "Project", filters=filters, fields=_fields(),
        start=start, page_length=page_length, order_by="modified desc",
    )
    _decorate_rows(rows, user)
    for r in rows:
        r["ec_personal_log"] = 1 if r["name"] in personal else 0

    total = frappe.db.count("Project", filters)
    return {"rows": rows, "total": total, "counts": counts}


@frappe.whitelist()
def get(name):
    """Project detail + task status breakdown. Permission-checked."""
    pmperm.require_pm_access()
    user = frappe.session.user
    _scope = pmperm.project_view_scope(name, user)  # throws if not permitted; None or own-task scope

    doc = frappe.get_doc("Project", name)
    counts = {}
    for t in frappe.get_all("Task", filters={"project": name}, or_filters=_scope, fields=["workflow_state"]):
        _ws = t["workflow_state"] or "—"
        counts[_ws] = counts.get(_ws, 0) + 1
    return {"project": doc.as_dict(), "task_status_counts": counts}


@frappe.whitelist()
def detail(name):
    """Project + risk summary (additive, permission-scoped). For UX-3 detail tabs.

    risk_level: high if overdue/blocked > 0; medium if many tasks lack assignee/due;
    low otherwise (risk_summary). progress = completed / total.
    Hotfix 23: project.color_key, can_manage, can_delete, health (hi|mid|ok|""), health_text.
    """
    pmperm.require_pm_access()
    user = frappe.session.user
    _scope = pmperm.project_view_scope(name, user)  # throws if not permitted; None or own-task scope

    doc = frappe.get_doc("Project", name)
    today = frappe.utils.nowdate()
    rows = frappe.get_all(
        "Task", filters={"project": name}, or_filters=_scope,
        fields=["name", "workflow_state", "exp_end_date", "_assign"],
        limit_page_length=0,
    )
    risk, level, total = risk_summary(rows, today)
    progress = int(round(risk["completed"] * 100.0 / total)) if total else 0
    health, health_text = health_of(risk, level, total, doc.get("status"))
    project = doc.as_dict()
    project["color_key"] = pmcolors.color_for(project)
    manage = can_manage_project(project, user)
    return {"project": project, "total": total, "risk": risk,
            "risk_level": level, "progress": progress,
            "health": health, "health_text": health_text, "can_manage": manage,
            "can_delete": bool(manage and not frappe.db.count("Task", {"project": name}))}


def _creator_department(user):
    try:
        return frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, "department") or None
    except Exception:
        return None


@frappe.whitelist()
def create(project_name, manager=None, department=None, expected_start_date=None,
           expected_end_date=None, priority=None, description=None):
    """Create a Project. ADOPTION-PHASE POLICY (G5.2): any enabled user with PM access may create a
    Project (Project DocPerm 'create' is granted to PM Member; delete/admin stay PM Manager/System
    Manager only). The creator becomes the project's ec_manager by default so they can see + manage
    it. Additive, native Project fields + existing custom ec_manager / ec_department. No schema.
    """
    pmperm.require_pm_access()  # any enabled user holding a PM role (PM Member/PM Manager/System Manager)
    user = frappe.session.user
    if not project_name:
        frappe.throw(frappe._("Project name is required."))
    if (expected_start_date and expected_end_date
            and str(expected_end_date) < str(expected_start_date)):
        frappe.throw(frappe._("End date cannot be before start date."))

    company = (frappe.defaults.get_user_default("Company")
               or frappe.db.get_single_value("Global Defaults", "default_company"))
    doc = frappe.get_doc({
        "doctype": "Project",
        "project_name": project_name,
        "status": "Open",
        "company": company,
        "expected_start_date": expected_start_date or None,
        "expected_end_date": expected_end_date or None,
        "priority": priority or None,
        "notes": description or None,
        "ec_manager": manager or user,        # G5.2: default creator as manager so they can see/manage
        # 26/11/2026: không chọn phòng ban -> lấy phòng ban của người tạo. Dự án không phòng ban chỉ người
        # tạo / quản lý / thành viên xem được (live: 9/44 dự án mở, đồng nghiệp cùng team bị chặn).
        "ec_department": department or _creator_department(user),
    })
    doc.insert()  # honors DocPerm 'create' + audit; ec_manager/ec_department validated by Frappe
    return {"name": doc.name, "project_name": doc.project_name}


@frappe.whitelist()
def update(name, project_name=None, manager=None, department=None,
           expected_start_date=None, expected_end_date=None, priority=None, description=None):
    """Edit a Project. Permitted for PM leaders (can_see_all_pm_data) OR the project's
    own ec_manager. Re-checked server-side per project (frontend hiding is not the gate).
    Full-form update: the edit modal always sends the complete editable field set, so each
    field is mapped from the payload. `name` (Project ID) is never changed. No schema.
    """
    pmperm.require_pm_access()
    user = frappe.session.user
    doc = frappe.get_doc("Project", name)
    is_leader = pmperm.can_see_all_pm_data(user)
    if not (is_leader or (doc.get("ec_manager") or None) == user):
        frappe.throw(frappe._("Only PM leaders or the project's manager can edit this project."),
                     frappe.PermissionError)
    if (expected_start_date and expected_end_date
            and str(expected_end_date) < str(expected_start_date)):
        frappe.throw(frappe._("End date cannot be before start date."))
    if project_name is not None:
        if not str(project_name).strip():
            frappe.throw(frappe._("Project name is required."))
        doc.project_name = project_name
    doc.ec_manager = manager or None
    doc.ec_department = department or None
    doc.expected_start_date = expected_start_date or None
    doc.expected_end_date = expected_end_date or None
    if priority:
        doc.priority = priority
    doc.notes = description or None
    _pin_status(doc)   # hotfix 23: editing a Completed project must not reopen it
    doc.save()  # honors audit; ec_manager/ec_department links validated by Frappe
    return {"name": doc.name, "project_name": doc.project_name}


@frappe.whitelist()
def set_status(name, status):
    """Hotfix 23: Hoàn thành / Huỷ / Mở lại a project. status in Open | Completed | Cancelled.
    Manager-or-leader only (can_manage_project, re-checked here). Validated doc.save() ->
    Version keeps who/when/from-to. Tasks are NOT touched (closing a project does not close
    its tasks)."""
    status = (status or "").strip()
    if status not in PROJECT_STATUSES:
        frappe.throw(_("Trạng thái dự án không hợp lệ: {0}").format(status or "-"))
    doc = _managed_doc(name, _("đổi trạng thái dự án"))
    if doc.get("status") != status:
        doc.status = status
        _pin_status(doc, force=True)
        doc.save()
    if doc.get("status") != status:
        frappe.throw(_("Chưa đổi được trạng thái dự án (hệ thống tự tính lại theo tiến độ). Thử lại hoặc báo quản trị."))
    return {"name": doc.name, "status": doc.get("status")}


def _pin_status(doc, force=False):
    """QC 27/11: ERPNext Project.validate -> update_percent_complete() re-derives status from task
    completion ("Completed" iff 100%, else "Open"; only Cancelled survives) unless the method is
    "Manual" - and every Task.on_update re-runs it via project.update_project(). A status chosen by a
    person (set_status) or an already-closed project being edited (colour / form) must not silently
    flip back, so switch the project to Manual. /pm shows progress from task counts, not percent_complete."""
    meta = getattr(doc, "meta", None)
    if meta is not None and hasattr(meta, "has_field") and not meta.has_field("percent_complete_method"):
        return
    if force or doc.get("status") == "Completed":
        if doc.get("percent_complete_method") != "Manual":
            doc.percent_complete_method = "Manual"


@frappe.whitelist()
def set_color(name, color_key=None):
    """Hotfix 23: project colour. color_key = one of colors.PALETTE_KEYS, or empty = back to the
    department colour. Same gate as projects.update (manager or PM leader). Returns the
    EFFECTIVE key (color_key) + the stored override (ec_color, "" = theo phòng ban)."""
    key = (color_key or "").strip()
    if key and not pmcolors.valid_key(key):
        frappe.throw(_("Màu không hợp lệ: {0}").format(key))
    doc = _managed_doc(name, _("đổi màu dự án"))
    if not pmcolors.has_color_field():
        frappe.throw(_("Hệ thống chưa cài trường màu dự án (Project.ec_color). Nhờ quản trị chạy cập nhật."))
    if (doc.get(pmcolors.COLOR_FIELD) or "") != key:
        doc.set(pmcolors.COLOR_FIELD, key)
        _pin_status(doc)
        doc.save()
    return {"name": doc.name, "color_key": pmcolors.color_for(doc), "ec_color": key}


@frappe.whitelist()
def delete(name):
    """Controlled hard-delete of a Project. Hotfix 23: PM leaders OR the project's manager
    (can_manage_project; was leader-only). Allowed ONLY when the project has zero Tasks
    (authoritative server-side count; never trusts the frontend). Uses the standard
    frappe.delete_doc (no SQL, no force) so Frappe's own link checks run — if any other
    document still links the project, a clear error is returned and nothing is cascade-deleted.
    """
    _managed_doc(name, _("xoá dự án"))
    task_count = frappe.db.count("Task", {"project": name})
    if task_count:
        frappe.throw(_("Dự án đã có {0} việc nên không xoá được. Hãy đánh dấu hoàn thành hoặc huỷ dự án.").format(task_count))
    try:
        frappe.delete_doc("Project", name, ignore_permissions=True)  # service layer is the gate; no force -> link checks apply
    except frappe.LinkExistsError:
        frappe.throw(_("Không thể xoá: dự án còn liên kết với dữ liệu khác. "
                       "Hãy gỡ liên kết hoặc đóng/huỷ dự án."))
    return {"deleted": name}


def _assert_can_tag(project):
    """Shared gate for project tag mutations: PM access + project visibility."""
    pmperm.require_pm_access()
    if not pmperm.can_view_project(project, frappe.session.user):
        frappe.throw(_("Không có quyền gắn nhãn dự án này."), frappe.PermissionError)


@frappe.whitelist()
def add_project_tag(project, tag):
    """Attach a tag (e.g. brand) to a Project via native Frappe tags (_user_tags)."""
    _assert_can_tag(project)
    tag = (tag or "").strip()
    if not tag:
        frappe.throw(_("Tên nhãn không được để trống."))
    from frappe.desk.doctype.tag.tag import DocTags
    DocTags("Project").add(project, tag)
    return {"project": project,
            "_user_tags": frappe.db.get_value("Project", project, "_user_tags")}


@frappe.whitelist()
def remove_project_tag(project, tag):
    """Remove a tag from a Project (native _user_tags)."""
    _assert_can_tag(project)
    tag = (tag or "").strip()
    from frappe.desk.doctype.tag.tag import DocTags
    DocTags("Project").remove(project, tag)
    return {"project": project,
            "_user_tags": frappe.db.get_value("Project", project, "_user_tags")}
