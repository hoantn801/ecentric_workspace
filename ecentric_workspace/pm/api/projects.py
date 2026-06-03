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
