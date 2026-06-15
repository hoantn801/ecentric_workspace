# Copyright (c) 2026, eCentric and contributors
"""WR1A service layer: ensure + close obligation.

Public API:
  ensure_weekly_obligation(schedule, week, now=None) -> str
      Idempotent. Returns one of: "created" | "adopted" | "reused" | "skipped".
      Raises MissingReportingWindowError (caller MUST handle).

  close_weekly_obligation(wtu_name)
      Called from events.on_weekly_update when WTU.status transitions to
      Submitted. Closes every Open obligation ToDo; raises on any error.

Lookup priority for ensure (matches Delta v3 sec. 3 + WR1A-V fixes):
  1. WTU by obligation_key (canonical)  - FIX 1: read full state, skip terminal
  2. WTU by (submitter, week_label) legacy  - FIX 5: limit 2, dup -> skip
  3. otherwise -> create new WTU Draft + ToDo

obligation_key = employee + "::" + week_label.

WR1A-V fixes in this revision:
  FIX 1: Canonical + legacy lookup return full state; terminal states
         (Submitted/Reviewed) never recreate a ToDo.
  FIX 3: close_weekly_obligation raises on ToDo without allocated_to (silent
         skip would violate "WTU Submitted => every Open Todo closed"
         invariant).
  FIX 4: Re-read Employee.status / Employee.user_id / User.enabled at
         generation time. Eligibility failure -> skipped (do NOT assign to
         stale user stored on Schedule).
  FIX 5: Legacy lookup limit 2; duplicate (submitter, week_label) -> skip.
"""

import frappe

from ecentric_workspace.weekly_report import week_calendar


WTU = "Weekly Team Update"

# Terminal WTU statuses: never recreate ToDo, never re-adopt.
TERMINAL_STATES = ("Submitted", "Reviewed")


class EligibilityError(Exception):
    """Raised when Employee/User mapping became invalid since Schedule create."""


def _obligation_key(employee, week_label):
    return str(employee) + "::" + str(week_label)


def _priority_from_due(due_at, now):
    """Map hours-to-deadline to ToDo priority."""
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


def _check_eligibility(schedule):
    """FIX 4: re-read Employee/User at generation time.

    Required conditions:
      Employee.status == "Active"
      Employee.user_id exists
      User.enabled == 1
      Employee.user_id == schedule.user (no mapping drift)

    Raises EligibilityError on any violation. Caller maps to "skipped".
    Stored Schedule.user is NOT trusted for the assignment; we use the
    re-read user_id.
    """
    emp_id = schedule.get("employee")
    schedule_user = schedule.get("user")
    if not emp_id:
        raise EligibilityError("Schedule missing employee")

    emp = frappe.db.get_value(
        "Employee", emp_id,
        ["status", "user_id"], as_dict=True,
    )
    if not emp:
        raise EligibilityError("Employee " + str(emp_id) + " not found")
    if emp.get("status") != "Active":
        raise EligibilityError(
            "Employee " + str(emp_id) + " status=" + str(emp.get("status")) + " (not Active)"
        )

    user_id = emp.get("user_id")
    if not user_id:
        raise EligibilityError("Employee " + str(emp_id) + " has no user_id")

    if schedule_user and user_id != schedule_user:
        raise EligibilityError(
            "Employee.user_id drift: schedule.user=" + str(schedule_user)
            + " current=" + str(user_id)
        )

    enabled = frappe.db.get_value("User", user_id, "enabled")
    if not enabled:
        raise EligibilityError("User " + str(user_id) + " disabled")

    return {"employee": emp_id, "user": user_id, "status": emp.get("status")}


def _ensure_todo(wtu_name, user, week, due_at, now):
    """Idempotent: create one Open ToDo for `user` if missing."""
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
    """FIX 1: return full state, not just name. Caller needs status to decide
    if terminal-state obligation should be left alone (no ToDo recreation).
    """
    key = _obligation_key(employee, week_label)
    return frappe.db.get_value(
        WTU,
        {"obligation_key": key},
        ["name", "status", "generated_obligation", "obligation_key"],
        as_dict=True,
    )


def _lookup_legacy(user, week_label):
    """FIX 5: detect duplicate legacy rows.

    Frappe WTU autoname is format:WTU-{week_label}-{employee}-{department}, so
    two WTUs with same (submitter, week_label) but DIFFERENT departments are
    schema-permitted. Adopting an arbitrary one would corrupt downstream
    lookups; we limit to 2 and skip on 2+ rows.
    """
    return frappe.get_all(
        WTU,
        filters={"submitter": user, "week_label": week_label},
        fields=["name", "status", "generated_obligation", "obligation_key"],
        limit_page_length=2,
        order_by="creation asc",
    )


def _set_obligation_fields(wtu_doc, schedule, week, due_at):
    wtu_doc.wr_schedule = schedule["name"]
    wtu_doc.due_at = due_at
    wtu_doc.generated_obligation = 1
    wtu_doc.obligation_key = _obligation_key(schedule["employee"], week["week_label"])


def ensure_weekly_obligation(schedule, week, now=None):
    """Idempotent per-schedule generator.

    Outcomes:
      "created"  - new WTU Draft + ToDo inserted
      "adopted"  - legacy Draft tagged + ToDo ensured
      "reused"   - already-generated Draft, ensured ToDo if absent
      "skipped"  - terminal WTU, ineligible Schedule, duplicate legacy, or
                   anomaly that needs human intervention
    """
    if now is None:
        now = frappe.utils.now_datetime()

    employee = schedule["employee"]
    department = schedule["reporting_department"]
    week_label = week["week_label"]
    week_start = week["week_start_date"]
    week_end = week["week_end_date"]

    # ---- FIX 4: revalidate Employee/User at generation time ---------------
    try:
        elig = _check_eligibility(schedule)
    except EligibilityError as e:
        frappe.log_error(
            "wr.ineligible schedule=" + str(schedule.get("name") or "?")
            + " employee=" + str(employee)
            + " err=" + str(e),
            "wr.ineligible",
        )
        return "skipped"
    user = elig["user"]  # use re-validated user, NOT stale schedule["user"]

    # DRW (after eligibility -- no wasted lookup on dead schedules).
    due_at = week_calendar.compute_due_at(week, department)

    emp_row = frappe.db.get_value(
        "Employee", employee,
        ["employee_name", "designation"], as_dict=True,
    ) or {}
    full_name = emp_row.get("employee_name") or ""
    designation = emp_row.get("designation") or ""

    # ---- 1. canonical lookup by obligation_key ---------------------------
    existing_by_key = _lookup_by_obligation_key(employee, week_label)
    if existing_by_key:
        status = existing_by_key.get("status") or "Draft"
        # FIX 1: terminal states -> never recreate ToDo
        if status in TERMINAL_STATES:
            return "skipped"
        if status == "Draft":
            _ensure_todo(existing_by_key["name"], user, week, due_at, now)
            return "reused"
        # Unknown status -> defensive skip
        frappe.log_error(
            "wr.unknown_status wtu=" + existing_by_key["name"]
            + " status=" + str(status),
            "wr.unknown_status",
        )
        return "skipped"

    # ---- 2. legacy lookup by (submitter, week_label) ---------------------
    legacy_rows = _lookup_legacy(user, week_label)
    # FIX 5: duplicate legacy -> skip + log
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
        # FIX 1: terminal states for legacy -> skip
        if status in TERMINAL_STATES:
            return "skipped"
        if legacy.get("generated_obligation"):
            expected_key = _obligation_key(employee, week_label)
            if (legacy.get("obligation_key") or "") != expected_key:
                frappe.log_error(
                    "wr.anomaly mismatched obligation_key wtu=" + legacy["name"]
                    + " expected=" + expected_key
                    + " actual=" + (legacy.get("obligation_key") or "<empty>"),
                    "wr.anomaly",
                )
                return "skipped"
            _ensure_todo(legacy["name"], user, week, due_at, now)
            return "reused"
        # Adopt.
        doc = frappe.get_doc(WTU, legacy["name"])
        _set_obligation_fields(doc, schedule, week, due_at)
        doc.save(ignore_permissions=True)
        _ensure_todo(doc.name, user, week, due_at, now)
        return "adopted"

    # ---- 3. create new WTU Draft + ToDo ----------------------------------
    new = frappe.get_doc({
        "doctype": WTU,
        "submitter": user,
        "employee": employee,
        "full_name": full_name,
        "department": department,
        "designation": designation,
        "week_label": week_label,
        "week_start_date": week_start,
        "week_end_date": week_end,
        "status": "Draft",
    })
    _set_obligation_fields(new, schedule, week, due_at)
    new.insert(ignore_permissions=True)
    _ensure_todo(new.name, user, week, due_at, now)
    return "created"


def close_weekly_obligation(wtu_name):
    """Close all open ToDos bound to this WTU.

    Invariant: WTU Submitted => every Open generated ToDo MUST be closed
    successfully. FIX 3: a ToDo with missing allocated_to cannot be closed via
    assign_to.remove (which requires a user); we raise rather than skip so the
    surrounding save() transaction rolls back (no WTU Submitted + dangling Open
    ToDo half-state).
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
        return  # idempotent: nothing open

    from frappe.desk.form.assign_to import remove as _assign_remove
    for t in todos:
        user = t.get("allocated_to")
        if not user:
            # FIX 3: invariant violation, NOT silent skip.
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
