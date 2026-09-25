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

from ecentric_workspace.weekly_report import (
    ai_retrigger,
    deck_sharing,
    due_backfill,
    scoring,
    sharepoint,
    submit_service,
)
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
def convert_decks_to_org_links(weeks=None, limit=25):
    """Share decks org-wide. Bulk write across employees -> System Manager only.

    weeks omitted -> rolling recent window (scheduler). weeks=["2026-W34",...]
    -> backfill those weeks only.
    """
    frappe.only_for("System Manager")
    if isinstance(weeks, str):
        weeks = json.loads(weeks) if weeks.strip().startswith("[") else [weeks]
    return deck_sharing.convert_pending(weeks=weeks, limit=int(limit or 25))


@frappe.whitelist(methods=["POST"])
def score_weekly_report(record_name=None):
    """Cham diem mot bao cao tuan qua Kie (Google du phong).

    Ghi vao ban ghi cua NGUOI KHAC (diem, tier, feedback) -> System Manager.
    Thay Server Script `gemini_score_report`, von goi thang Google tu sandbox va
    mat sach ly do loi khi Google tra 4xx.
    """
    frappe.only_for("System Manager")
    if not record_name:
        frappe.throw(_("record_name is required."))
    return scoring.score_report(record_name)


@frappe.whitelist(methods=["POST"])
def summarize_weekly_report(record_name=None):
    """Tom tat mot bao cao tuan. Cung ly do phan quyen nhu score_weekly_report."""
    frappe.only_for("System Manager")
    if not record_name:
        frappe.throw(_("record_name is required."))
    return scoring.summarize_report(record_name)


@frappe.whitelist(methods=["POST"])
def retrigger_missing_ai(window_days=None, limit=None):
    """Cham bu diem/tom tat con thieu. Ruot cua cron auto_retrigger_missing_ai.

    Mac dinh nho (4 ban/luot) vi rq worker giet job o 300 giay. Backlog thi dung
    rescore_from_week.ps1, khong phai ha limit o day roi doi cron chay bu.

    Administrator duoc mien kiem tra role: scheduler chay duoi danh nghia do, va
    mot cron bi chinh cong phan quyen cua no chan lai thi khong chay, khong bao,
    chi de lai mot con so 0 trong thong ke - dung kieu hong da mat ca tuan de
    truy ra hoi 15/09.
    """
    if frappe.session.user != "Administrator":
        frappe.only_for("System Manager")
    kwargs = {}
    if window_days:
        kwargs["window_days"] = int(window_days)
    if limit:
        kwargs["limit"] = int(limit)
    return ai_retrigger.run(**kwargs)


@frappe.whitelist(methods=["POST"])
def backfill_weekly_due_at(weeks=None, limit=500, dry_run=1, skip_if_late=0):
    """Fill missing `due_at` on Weekly Team Update rows. Reports by default.

    Writes across other people's records -> System Manager only.

    dry_run defaults to 1 and must be passed 0 EXPLICITLY to write anything.
    The report carries `would_be_late`: rows whose author becomes late once
    given a deadline. Read that number before writing -- the missing deadline
    was our bug, not theirs.
    """
    frappe.only_for("System Manager")
    if isinstance(weeks, str):
        weeks = json.loads(weeks) if weeks.strip().startswith("[") else [weeks]
    return due_backfill.backfill(
        weeks=weeks,
        limit=int(limit or 500),
        dry_run=bool(int(dry_run)),
        skip_if_late=bool(int(skip_if_late)),
    )


@frappe.whitelist(methods=["POST"])
def submit_weekly_update(data=None):
    """Persist a weekly update. `data` is the JSON payload as a string."""
    payload = _parse_payload(data)
    _assert_can_submit_for(payload.get("employee"))
    try:
        return submit_service.submit(payload)
    except submit_service.SubmitError as exc:
        return {"success": False, "error": str(exc)}
