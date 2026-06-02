"""PM v2 - Dashboard summary service.

Real logic lands in PM1-T09. Returns {my_tasks, team_tasks, overdue,
due_this_week} as permission-filtered counts + top N. Definitions:
  my_tasks      - _assign contains current user
  team_tasks    - tasks in projects where user is manager/member
  overdue       - exp_end_date < today AND status NOT IN (Completed, Cancelled)
  due_this_week - exp_end_date BETWEEN today AND today + 7 days

Module path: ecentric_workspace.pm.api.dashboard
Status: PM1-T00 scaffold. NOT wired into hooks.py. NOT deployed.
"""

import frappe


@frappe.whitelist()
def summary():
    """Stub for PM1-T09. No data access yet."""
    return {"ok": True, "service": "dashboard.summary", "implemented": False}
