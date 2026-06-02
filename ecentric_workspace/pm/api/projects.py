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
