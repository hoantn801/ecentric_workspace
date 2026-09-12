# Copyright (c) 2026, eCentric and contributors
"""Weekly Report API.

Endpoints:
  POST .../api.run_weekly_report_pilot
  body: {"employee": "<Employee record name>"}

  POST .../api.create_deck_upload_session
  body: {filename, week_label, employee, department}
  -> {"success": true, "upload_url": "<Graph upload URL>"}
  The BROWSER then PUTs the deck bytes to that URL (A21) -- they never pass
  through this server.

  POST .../api.submit_weekly_update
  body: {"data": "<json payload incl. deck_urls:[{name, web_url}]>"}
  Replaces the Server Script of the same name (A57): the sandbox lost
  frappe.request in the python3.14 upgrade, so it could no longer read
  uploaded files at all.

Guard rails:
  - System Manager role only.
  - Single Employee only; lists / iterables are rejected.
  - Employee must exist.
  - Kill-switch (enable_weekly_report_auto_generation) is NOT toggled.
    Pilot bypasses it via the employee_names path in
    generate_weekly_obligations().
  - Reuses scheduler/service unchanged. No new code path.
"""

import json

import frappe
from frappe import _

from ecentric_workspace.weekly_report import sharepoint, submit_service
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


def _parse_payload(data):
    if isinstance(data, dict):
        return data
    try:
        payload = json.loads(data or "{}")
    except (TypeError, ValueError):
        frappe.throw(_("Invalid payload."))
    if not isinstance(payload, dict):
        frappe.throw(_("Invalid payload."))
    return payload


def _dept_clean(department):
    dept = department or "Unknown"
    return dept.rsplit(" - ", 1)[0] if " - " in dept else dept


def _assert_can_submit_for(employee):
    """A weekly report may only be filed by its owner (or a System Manager).

    BEHAVIOUR CHANGE vs the Server Script being replaced: that one trusted the
    client-supplied `employee` outright, so any signed-in user could write a
    report onto anyone else's record. If submitting on behalf of others is a
    real workflow (W38 showed a record whose submitter was a shared CnB
    account), whitelist that role here before cutover.
    """
    if not employee:
        frappe.throw(_("Employee is required."))
    if frappe.db.get_value("Employee", employee, "user_id") == frappe.session.user:
        return
    if "System Manager" in frappe.get_roles():
        return
    frappe.throw(
        _("You cannot submit a weekly report for another employee."),
        frappe.PermissionError,
    )


@frappe.whitelist(methods=["POST"])
def create_deck_upload_session(filename=None, week_label=None, employee=None, department=None):
    """Hand the browser a Graph upload URL; the deck never touches this server."""
    _assert_can_submit_for(employee)
    if not filename or not week_label:
        frappe.throw(_("filename and week_label are required."))
    emp_code = frappe.db.get_value("Employee", employee, "employee_number") or "unknown"
    rel_path = sharepoint.build_deck_path(
        week_label, emp_code, _dept_clean(department), filename
    )
    token = sharepoint.get_app_token()
    return {
        "success": True,
        "upload_url": sharepoint.create_deck_upload_session(rel_path, token),
    }


@frappe.whitelist(methods=["POST"])
def submit_weekly_update(data=None):
    """Persist a weekly update. `data` is the JSON payload as a string."""
    payload = _parse_payload(data)
    _assert_can_submit_for(payload.get("employee"))
    try:
        return submit_service.submit(payload)
    except submit_service.SubmitError as exc:
        return {"success": False, "error": str(exc)}
