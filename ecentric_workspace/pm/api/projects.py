"""PM v2 - Project read services (PM1-T05).

Permission enforced in this service layer via ecentric_workspace.pm.permissions
(department-based scope). No global permission_query_conditions are used.

Module path: ecentric_workspace.pm.api.projects
"""

import frappe

from ecentric_workspace.pm import permissions as pmperm

_FIELDS = [
    "name", "project_name", "status", "percent_complete",
    "ec_department", "ec_manager", "owner", "modified",
]


@frappe.whitelist()
def list(start=0, page_length=20, status=None):
    """Permission-scoped, paginated project list. Returns {rows, total}."""
    pmperm.require_pm_access()
    user = frappe.session.user

    filters = {}
    if status:
        filters["status"] = status

    visible = pmperm.get_visible_project_names(user)
    if visible is not None:
        if not visible:
            return {"rows": [], "total": 0}
        filters["name"] = ["in", visible]

    rows = frappe.get_all(
        "Project", filters=filters, fields=_FIELDS,
        start=int(start), page_length=int(page_length), order_by="modified desc",
    )
    # Computed progress from task completion (native percent_complete is unreliable
    # here since PM uses workflow_state). Same definition as projects.detail:
    # progress = Done / total_tasks. Single aggregate query for the page's projects.
    names = [r["name"] for r in rows]
    if names:
        agg = {}
        for t in frappe.get_all(
            "Task", filters={"project": ["in", names]},
            fields=["project", "workflow_state"], limit_page_length=0,
        ):
            a = agg.setdefault(t["project"], {"total": 0, "done": 0})
            a["total"] += 1
            if t.get("workflow_state") == "Done":
                a["done"] += 1
        for r in rows:
            a = agg.get(r["name"], {"total": 0, "done": 0})
            r["task_total"] = a["total"]
            r["task_done"] = a["done"]
            r["progress"] = int(round(a["done"] * 100.0 / a["total"])) if a["total"] else 0

    total = frappe.db.count("Project", filters)
    return {"rows": rows, "total": total}


@frappe.whitelist()
def get(name):
    """Project detail + task status breakdown. Permission-checked."""
    pmperm.require_pm_access()
    user = frappe.session.user
    if not pmperm.can_view_project(name, user):
        frappe.throw(frappe._("Not permitted to view this project."), frappe.PermissionError)

    doc = frappe.get_doc("Project", name)
    counts = {}
    for t in frappe.get_all("Task", filters={"project": name}, fields=["status"]):
        counts[t["status"]] = counts.get(t["status"], 0) + 1
    return {"project": doc.as_dict(), "task_status_counts": counts}


_FINISHED = ["Done", "Cancelled"]


@frappe.whitelist()
def detail(name):
    """Project + risk summary (additive, permission-scoped). For UX-3 detail tabs.

    risk_level: high if overdue/blocked > 0; medium if many tasks lack assignee/due;
    low otherwise. progress = completed / total.
    """
    pmperm.require_pm_access()
    user = frappe.session.user
    if not pmperm.can_view_project(name, user):
        frappe.throw(frappe._("Not permitted to view this project."), frappe.PermissionError)

    doc = frappe.get_doc("Project", name)
    today = frappe.utils.nowdate()
    rows = frappe.get_all(
        "Task", filters={"project": name},
        fields=["name", "workflow_state", "exp_end_date", "_assign"],
        limit_page_length=0,
    )

    def assignees(t):
        try:
            return frappe.parse_json(t.get("_assign") or "[]") or []
        except Exception:
            return []

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
        "no_assignee": len([t for t in rows if not assignees(t)]),
        "no_due": len([t for t in rows if not t.get("exp_end_date")]),
        "completed": len([t for t in rows if t.get("workflow_state") == "Done"]),
    }
    if risk["overdue"] > 0 or risk["blocked"] > 0:
        level = "high"
    elif (risk["no_assignee"] + risk["no_due"]) >= max(3, total // 2):
        level = "medium"
    else:
        level = "low"
    progress = int(round(risk["completed"] * 100.0 / total)) if total else 0
    return {"project": doc.as_dict(), "total": total, "risk": risk,
            "risk_level": level, "progress": progress}


@frappe.whitelist()
def create(project_name, manager=None, department=None, expected_start_date=None,
           expected_end_date=None, priority=None, description=None):
    """Create a Project. LEADER-ONLY (Management dept or System Manager) — Project is a
    master object. Additive, native Project fields + existing custom ec_manager /
    ec_department (Link Department). No schema change.
    """
    pmperm.require_pm_access()
    user = frappe.session.user
    if not pmperm.can_see_all_pm_data(user):
        frappe.throw(frappe._("Only PM leaders can create projects."), frappe.PermissionError)
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
        "ec_manager": manager or None,        # existing custom field (Link User)
        "ec_department": department or None,   # existing custom field (Link Department)
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
    doc.save()  # honors audit; ec_manager/ec_department links validated by Frappe
    return {"name": doc.name, "project_name": doc.project_name}


@frappe.whitelist()
def delete(name):
    """Controlled hard-delete of a Project. LEADER-ONLY. Allowed ONLY when the project
    has zero Tasks (authoritative server-side count; never trusts the frontend). Uses the
    standard frappe.delete_doc (no SQL, no force) so Frappe's own link checks run — if any
    other document still links the project, a clear error is returned and nothing is
    cascade-deleted.
    """
    pmperm.require_pm_access()
    user = frappe.session.user
    if not pmperm.can_see_all_pm_data(user):
        frappe.throw(frappe._("Only PM leaders can delete projects."), frappe.PermissionError)
    if not frappe.db.exists("Project", name):
        frappe.throw(frappe._("Project not found."))
    task_count = frappe.db.count("Task", {"project": name})
    if task_count:
        frappe.throw(frappe._("Dự án đã có nhiệm vụ và không thể xoá. Hãy đóng hoặc huỷ dự án."))
    try:
        frappe.delete_doc("Project", name, ignore_permissions=True)  # service layer is the gate; no force -> link checks apply
    except frappe.LinkExistsError:
        frappe.throw(frappe._("Không thể xoá: dự án còn liên kết với dữ liệu khác. "
                              "Hãy gỡ liên kết hoặc đóng/huỷ dự án."))
    return {"deleted": name}
