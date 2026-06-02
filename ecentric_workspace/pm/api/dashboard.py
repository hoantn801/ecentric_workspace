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

_FINISHED = ["Completed", "Cancelled"]


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

    overdue_f = {"exp_end_date": ["<", today], "status": ["not in", _FINISHED]}
    week_f = {"exp_end_date": ["between", [today, week]], "status": ["not in", _FINISHED]}

    return {
        "my_tasks": _count(None, mine),
        "team_tasks": _count(None, scope),
        "overdue": _count(overdue_f, scope),
        "due_this_week": _count(week_f, scope),
        "scope": "all" if scope is None else "department",
    }
