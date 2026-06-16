# Copyright (c) 2026, eCentric and contributors
"""WR Hotfix service: Employee-driven ensure + close obligation.

Public API:
  ensure_weekly_obligation(employee, week, now=None) -> str
      Idempotent. Returns "created" | "adopted" | "reused" | "skipped".
      Raises MissingReportingWindowError.

  close_weekly_obligation(wtu_name)
      Closes every open obligation ToDo; raises on any error (no silent
      half-state).

Eligibility check (all required for non-skipped outcome):
  Employee.status == "Active"
  Employee.user_id exists
  User.enabled == 1
  Employee.department exists

obligation_key = employee + "::" + week_label.

Lookup priority for ensure:
  1. Canonical: WTU by obligation_key -- terminal (Submitted/Reviewed) skipped
  2. Legacy:    WTU by (submitter, week_label), limit 2 -- 2+ rows skipped,
                terminal skipped, generated_obligation=0 Draft adopted.
  3. Create:    new WTU Draft + ToDo. wr_schedule field NOT set (deprecated).
"""

import frappe

from ecentric_workspace.weekly_report import week_calendar


WTU = "Weekly Team Update"
TERMINAL_STATES = ("Submitted", "Reviewed")


class EligibilityError(Exception):
    """Raised when Employee/User/Department mapping is invalid."""


def _obligation_key(employee, week_label):
    return str(employee) + "::" + str(week_label)


def _priority_from_due(due_at, now):
    if due_at is None or now is None:
        return "Medium"
    delta_hours = (due_at - now).total_seconds() / 3600.0
    if delta_hours <= 24:
        return "High"
    if delta_hours <= 72:
        return "Medium"
    return "Low"


def _todo_description(week, due_at):
    label = week["week_label"]
    href = "/weekly-update?week=" + label
    due_disp = ""
    try:
        due_disp = frappe.utils.format_datetime(due_at, "EEE dd/MM/yyyy HH:mm")
    except Exception:
        due_disp = str(due_at)
    return (
        '<b>Bao cao tuan ' + label + '</b><br>'
        + 'Han nop: ' + due_disp + '<br>'
        + '<a href="' + href + '">Mo bao cao</a>'
    )


def _check_employee_eligibility(employee):
    """Read Employee + User; raise EligibilityError on any violation.

    Returns: {user, department, full_name, designation}.
    """
    emp = frappe.db.get_value(
        "Employee", employee,
        ["status", "user_id", "department", "employee_name", "designation"],
        as_dict=True,
    )
    if not emp:
        raise EligibilityError("Employee " + str(employee) + " not found")
    if emp.get("status") != "Active":
        raise EligibilityError(
            "Employee " + str(employee) + " status=" + str(emp.get("status")) + " (not Active)"
        )
    user_id = emp.get("user_id")
    if not user_id:
        raise EligibilityError("Employee " + str(employee) + " has no user_id")
    if not emp.get("department"):
        raise EligibilityError("Employee " + str(employee) + " has no department")
    enabled = frappe.db.get_value("User", user_id, "enabled")
    if not enabled:
        raise EligibilityError("User " + str(user_id) + " disabled")
    return {
        "user": user_id,
        "department": emp.get("department"),
        "full_name": emp.get("employee_name") or "",
        "designation": emp.get("designation") or "",
    }


def _ensure_todo(wtu_name, user, week, due_at, now):
    existing = frappe.get_all(
        "ToDo",
        filters={
            "reference_type": WTU,
            "reference_name": wtu_name,
            "status": "Open",
            "allocated_to": user,
        },
        limit_page_length=1,
    )
    if existing:
        return False
    from frappe.desk.form.assign_to import add as _assign_add
    _assign_add({
        "doctype": WTU,
        "name": wtu_name,
        "assign_to": [user],
        "description": _todo_description(week, due_at),
        "priority": _priority_from_due(due_at, now),
        "date": str(due_at.date()) if due_at else None,
        "notify": 0,
        "assigned_by": "Administrator",
    })
    return True


def _lookup_by_obligation_key(employee, week_label):
    key = _obligation_key(employee, week_label)
    return frappe.db.get_value(
        WTU,
        {"obligation_key": key},
        ["name", "status", "generated_obligation", "obligation_key"],
        as_dict=True,
    )


def _lookup_legacy(user, week_label):
    return frappe.get_all(
        WTU,
        filters={"submitter": user, "week_label": week_label},
        fields=["name", "status", "generated_obligation", "obligation_key"],
        limit_page_length=2,
        order_by="creation asc",
    )


def _set_obligation_fields(wtu_doc, employee, week, due_at):
    """Hotfix: wr_schedule no longer set; field deprecated."""
    wtu_doc.due_at = due_at
    wtu_doc.generated_obligation = 1
    wtu_doc.obligation_key = _obligation_key(employee, week["week_label"])


def ensure_weekly_obligation(employee, week, now=None):
    """Employee-driven idempotent per-row generator.

    Args:
        employee: Employee DocType record name (str).
        week:     dict from week_calendar.compute_week_for().
        now:      datetime (defaults to site-tz now).
    """
    if now is None:
        now = frappe.utils.now_datetime()

    week_label = week["week_label"]
    week_start = week["week_start_date"]
    week_end = week["week_end_date"]

    # Eligibility
    try:
        elig = _check_employee_eligibility(employee)
    except EligibilityError as exc:
        frappe.log_error(
            "wr.ineligible employee=" + str(employee) + " err=" + str(exc),
            "wr.ineligible",
        )
        return "skipped"
    user = elig["user"]
    department = elig["department"]

    # DRW lookup (raises MissingReportingWindowError if missing OR disabled)
    due_at = week_calendar.compute_due_at(week, department)

    # ---- 1. canonical lookup ----
    existing_by_key = _lookup_by_obligation_key(employee, week_label)
    if existing_by_key:
        status = existing_by_key.get("status") or "Draft"
        if status in TERMINAL_STATES:
            return "skipped"
        if status == "Draft":
            _ensure_todo(existing_by_key["name"], user, week, due_at, now)
            return "reused"
        frappe.log_error(
            "wr.unknown_status wtu=" + existing_by_key["name"]
            + " status=" + str(status),
            "wr.unknown_status",
        )
        return "skipped"

    # ---- 2. legacy lookup ----
    legacy_rows = _lookup_legacy(user, week_label)
    if len(legacy_rows) >= 2:
        names = ",".join([r.get("name", "?") for r in legacy_rows])
        frappe.log_error(
            "wr.duplicate_legacy count=" + str(len(legacy_rows))
            + " submitter=" + str(user) + " week=" + week_label
            + " rows=" + names,
            "wr.duplicate_legacy",
        )
        return "skipped"
    if legacy_rows:
        legacy = legacy_rows[0]
        status = legacy.get("status") or "Draft"
        if status in TERMINAL_STATES:
            return "skipped"
        if legacy.get("generated_obligation"):
            expected_key = _obligation_key(employee, week_label)
            if (legacy.get("obligation_key") or "") != expected_key:
                frappe.log_error(
                    "wr.anomaly wtu=" + legacy["name"]
                    + " expected=" + expected_key
                    + " actual=" + (legacy.get("obligation_key") or "<empty>"),
                    "wr.anomaly",
                )
                return "skipped"
            _ensure_todo(legacy["name"], user, week, due_at, now)
            return "reused"
        # Adopt legacy Draft.
        doc = frappe.get_doc(WTU, legacy["name"])
        _set_obligation_fields(doc, employee, week, due_at)
        doc.save(ignore_permissions=True)
        _ensure_todo(doc.name, user, week, due_at, now)
        return "adopted"

    # ---- 3. create new ----
    new = frappe.get_doc({
        "doctype": WTU,
        "submitter": user,
        "employee": employee,
        "full_name": elig["full_name"],
        "department": department,
        "designation": elig["designation"],
        "week_label": week_label,
        "week_start_date": week_start,
        "week_end_date": week_end,
        "status": "Draft",
    })
    _set_obligation_fields(new, employee, week, due_at)
    new.insert(ignore_permissions=True)
    _ensure_todo(new.name, user, week, due_at, now)
    return "created"


def close_weekly_obligation(wtu_name):
    """Close all open ToDos bound to this WTU.

    Invariant: WTU Submitted => every Open generated ToDo MUST be closed
    successfully. ToDo without allocated_to raises (invariant violation,
    NOT silent skip).
    """
    todos = frappe.get_all(
        "ToDo",
        filters={
            "reference_type": WTU,
            "reference_name": wtu_name,
            "status": "Open",
        },
        fields=["name", "allocated_to"],
    )
    if not todos:
        return

    from frappe.desk.form.assign_to import remove as _assign_remove
    for t in todos:
        user = t.get("allocated_to")
        if not user:
            msg = ("wr.close ToDo " + t["name"]
                   + " has no allocated_to; cannot close via assign_to API")
            frappe.log_error(msg, "wr.close")
            raise frappe.ValidationError(msg)
        try:
            _assign_remove(WTU, wtu_name, user)
            td = frappe.get_doc("ToDo", t["name"])
            td.status = "Closed"
            td.save(ignore_permissions=True)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "wr.close " + t["name"])
            raise
