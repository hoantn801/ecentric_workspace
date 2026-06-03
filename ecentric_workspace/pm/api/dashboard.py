"""PM v2 - Dashboard summary service (PM1-T05).

Permission-scoped counts via ecentric_workspace.pm.permissions (service layer).
Definitions:
  my_tasks      - tasks assigned to the current user (_assign)
  team_tasks    - in-scope tasks (own / assigned / visible project)
  overdue       - in-scope, exp_end_date < today, status NOT IN (Completed, Cancelled)
  due_this_week - in-scope, today <= exp_end_date <= today + 7, not finished

Module path: ecentric_workspace.pm.api.dashboard
"""

import frappe

from ecentric_workspace.pm import permissions as pmperm

# PM workflow terminal states (PM1-T07). PM status is workflow_state, NOT native
# Task.status (which ERPNext manages on its own).
_FINISHED = ["Done", "Cancelled"]


def _count(and_filters, or_filters):
    rows = frappe.get_all(
        "Task", filters=and_filters or None, or_filters=or_filters,
        fields=["name"], limit_page_length=0,
    )
    return len(rows)


@frappe.whitelist()
def summary():
    pmperm.require_pm_access()
    user = frappe.session.user
    today = frappe.utils.nowdate()
    week = frappe.utils.add_days(today, 7)

    scope = pmperm.task_scope_or_filters(user)  # None = all in PM
    mine = [["_assign", "like", "%{0}%".format(user)]]

    overdue_f = {"exp_end_date": ["<", today], "workflow_state": ["not in", _FINISHED]}
    week_f = {"exp_end_date": ["between", [today, week]], "workflow_state": ["not in", _FINISHED]}

    return {
        "my_tasks": _count(None, mine),
        "team_tasks": _count(None, scope),
        "overdue": _count(overdue_f, scope),
        "due_this_week": _count(week_f, scope),
        "scope": "all" if scope is None else "department",
    }


def _assignees(t):
    try:
        return frappe.parse_json(t.get("_assign") or "[]") or []
    except Exception:
        return []


def _slim(rows):
    out = []
    for t in rows:
        out.append({
            "name": t["name"], "subject": t.get("subject"), "project": t.get("project"),
            "workflow_state": t.get("workflow_state"),
            "exp_end_date": str(t["exp_end_date"])[:10] if t.get("exp_end_date") else None,
            "_assign": t.get("_assign"), "priority": t.get("priority"),
        })
    return out


@frappe.whitelist()
def control_center():
    """My Work (everyone) + Team Overview & Workload (leaders only). Permission-scoped."""
    pmperm.require_pm_access()
    user = frappe.session.user
    today = frappe.utils.nowdate()
    week_end = frappe.utils.add_days(today, 7)
    FIELDS = ["name", "subject", "project", "workflow_state", "exp_end_date",
              "_assign", "priority", "modified"]

    def d10(t):
        v = t.get("exp_end_date")
        return str(v)[:10] if v else None

    def is_active(t):
        return t.get("workflow_state") not in _FINISHED

    def is_overdue(t):
        dd = d10(t)
        return bool(dd and dd < today and is_active(t))

    def is_today(t):
        return d10(t) == today and is_active(t)

    def is_week(t):
        dd = d10(t)
        return bool(dd and today <= dd <= week_end and is_active(t))

    mine = frappe.get_all("Task", filters=[["_assign", "like", "%" + user + "%"]],
                          fields=FIELDS, limit_page_length=0)
    my_overdue = [t for t in mine if is_overdue(t)]
    my_review = [t for t in mine if t.get("workflow_state") == "Review"]
    my_blocked = [t for t in mine if t.get("workflow_state") == "Blocked"]
    my_counts = {
        "overdue": len(my_overdue),
        "today": len([t for t in mine if is_today(t)]),
        "week": len([t for t in mine if is_week(t)]),
        "review": len(my_review),
        "blocked": len(my_blocked),
    }

    timer = None
    if frappe.db.exists("PM Timer", user):
        tt = frappe.get_doc("PM Timer", user)
        timer = {"task": tt.task, "status": tt.status}
    unread = frappe.db.count("Notification Log",
                             {"for_user": user, "document_type": "Task", "read": 0})

    out = {
        "is_leader": pmperm.can_see_all_pm_data(user),
        "unread": unread, "timer": timer,
        "my": {"counts": my_counts, "overdue": _slim(my_overdue),
               "review": _slim(my_review), "blocked": _slim(my_blocked)},
    }

    if pmperm.can_see_all_pm_data(user):
        allt = frappe.get_all("Task", fields=FIELDS, limit_page_length=0)
        wstart = frappe.utils.add_days(today, -frappe.utils.getdate(today).weekday())
        out["team"] = {
            "active": len([t for t in allt if is_active(t)]),
            "overdue": len([t for t in allt if is_overdue(t)]),
            "blocked": len([t for t in allt if t.get("workflow_state") == "Blocked"]),
            "review": len([t for t in allt if t.get("workflow_state") == "Review"]),
            "no_assignee": len([t for t in allt if not _assignees(t)]),
            "no_due": len([t for t in allt if not t.get("exp_end_date")]),
            "completed_week": len([t for t in allt if t.get("workflow_state") == "Done"
                                   and str(t.get("modified") or "")[:10] >= wstart]),
        }
        wl = {}
        for t in allt:
            for u in _assignees(t):
                w = wl.setdefault(u, {"assignee": u, "active": 0, "overdue": 0,
                                      "due_week": 0, "in_progress": 0, "blocked": 0})
                if is_active(t):
                    w["active"] += 1
                if is_overdue(t):
                    w["overdue"] += 1
                if is_week(t):
                    w["due_week"] += 1
                if t.get("workflow_state") == "In Progress":
                    w["in_progress"] += 1
                if t.get("workflow_state") == "Blocked":
                    w["blocked"] += 1
        out["workload"] = sorted(wl.values(), key=lambda x: -x["active"])
        out["attention"] = {
            "overdue": _slim([t for t in allt if is_overdue(t)][:10]),
            "blocked": _slim([t for t in allt if t.get("workflow_state") == "Blocked"][:10]),
            "review": _slim([t for t in allt if t.get("workflow_state") == "Review"][:10]),
        }
    return out
