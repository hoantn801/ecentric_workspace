# Copyright (c) 2026, eCentric and contributors
"""Production-safe pilot API for the Weekly Report scheduler.

Endpoint:
  POST /api/method/ecentric_workspace.weekly_report.api.run_weekly_report_pilot
  body: {"employee": "<Employee record name>"}

Guard rails:
  - System Manager role only.
  - Single Employee only; lists / iterables are rejected.
  - Employee must exist.
  - Kill-switch (enable_weekly_report_auto_generation) is NOT toggled.
    Pilot bypasses it via the employee_names path in
    generate_weekly_obligations().
  - Reuses scheduler/service unchanged. No new code path.
"""

import frappe
from frappe import _

from ecentric_workspace.weekly_report.scheduler import generate_weekly_obligations


@frappe.whitelist(methods=["POST"])
def run_weekly_report_pilot(employee=None):
    """Run the weekly-report generator for exactly one Employee.

    Returns the stats dict from generate_weekly_obligations(). Safe to call
    repeatedly: idempotent per Employee + week.
    """
    frappe.only_for("System Manager")

    # Reject lists / iterables; pilot is single-Employee on purpose.
    if isinstance(employee, (list, tuple, set, dict)):
        frappe.throw(_("Pilot accepts a single Employee, not a collection."))

    if not employee or not isinstance(employee, str) or not employee.strip():
        frappe.throw(_("Employee is required."))

    employee = employee.strip()
    if not frappe.db.exists("Employee", employee):
        frappe.throw(_("Employee {0} not found.").format(employee))

    return generate_weekly_obligations(employee_names=[employee])
