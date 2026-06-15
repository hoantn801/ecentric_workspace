# Copyright (c) 2026, eCentric and contributors
"""WR1A service layer: ensure + close obligation.

Public API:
  ensure_weekly_obligation(schedule, week) -> str
      Idempotent. Returns one of: "created" | "adopted" | "reused" | "skipped".
      Raises MissingReportingWindowError (caller MUST handle).

  close_weekly_obligation(wtu_name)
      Called from events.on_weekly_update when WTU.status transitions to
      Submitted. For each open ToDo bound to this WTU:
        1. assign_to.remove   -> clears _assign + sets ToDo.status = Cancelled
        2. reload ToDo
        3. set status = "Closed"
        4. todo.save(ignore_permissions=True)
      Any step error -> log + raise (do NOT swallow; transaction must roll back
      so the WTU does NOT end up Submitted with the ToDo still Open).

Lookup priority for ensure (matches Delta v3 sec. 3):
  1. WTU by obligation_key (canonical)
  2. WTU by (submitter, week_label) legacy lookup
     - Submitted    -> skip
     - Draft, generated_obligation=0  -> adopt (set wr fields, ensure ToDo)
     - Draft, generated_obligation=1, obligation_key mismatch -> anomaly-skip
  3. otherwise   -> create new WTU Draft + ToDo

obligation_key = employee + "::" + week_label.
"""

import frappe

from ecentric_workspace.weekly_report import week_calendar


WTU = "Weekly Team Update"


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
    # Plain ASCII fallback if vi text causes issues; description is Text Editor
    # so HTML is allowed.
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


def _ensure_todo(wtu_name, user, week, due_at, now):
    """Idempotent: create one Open ToDo if missing."""
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
    return frappe.db.get_value(WTU, {"obligation_key": key}, "name")


def _lookup_legacy(user, week_label):
    """Match the existing submit_weekly_update lookup: by (submitter, week_label)."""
    return frappe.db.get_value(
        WTU,
        {"submitter": user, "week_label": week_label},
        ["name", "status", "generated_obligation", "obligation_key"],
        as_dict=True,
    )


def _set_obligation_fields(wtu_doc, schedule, week, due_at):
    wtu_doc.wr_schedule = schedule["name"]
    wtu_doc.due_at = due_at
    wtu_doc.generated_obligation = 1
    wtu_doc.obligation_key = _obligation_key(schedule["employee"], week["week_label"])


def ensure_weekly_obligation(schedule, week, now=None):
    """Idempotent per-schedule generator.

    schedule: dict with keys name, employee, user, reporting_department,
              effective_from, effective_to, last_generated_week.
    week:     dict from week_calendar.compute_week_for().
    now:      datetime for tests/manual rerun. Defaults to site-tz now.

    Returns:
      "created"   - new WTU Draft + ToDo inserted
      "adopted"   - legacy Draft tagged + ToDo ensured
      "reused"    - already-generated, ensured ToDo if absent
      "skipped"   - legacy Submitted, anomaly, or no-op
    """
    if now is None:
        now = frappe.utils.now_datetime()

    employee = schedule["employee"]
    user = schedule["user"]
    department = schedule["reporting_department"]
    week_label = week["week_label"]
    week_start = week["week_start_date"]
    week_end = week["week_end_date"]

    # Resolve DRW first; missing DRW -> raise (caller logs + rolls back).
    due_at = week_calendar.compute_due_at(week, department)

    # Resolve display fields from Employee (snapshot at generation time).
    emp_row = frappe.db.get_value(
        "Employee", employee,
        ["employee_name", "designation"], as_dict=True
    ) or {}
    full_name = emp_row.get("employee_name") or ""
    designation = emp_row.get("designation") or ""

    # ---- 1. canonical lookup by obligation_key -----------------------------
    existing_by_key = _lookup_by_obligation_key(employee, week_label)
    if existing_by_key:
        # Ensure ToDo is present (covers case where ToDo was somehow lost).
        _ensure_todo(existing_by_key, user, week, due_at, now)
        return "reused"

    # ---- 2. legacy lookup by (submitter, week_label) -----------------------
    legacy = _lookup_legacy(user, week_label)
    if legacy:
        status = legacy.get("status") or "Draft"
        if status == "Submitted":
            return "skipped"
        # Draft path
        if legacy.get("generated_obligation"):
            # Already tagged but key mismatch -> anomaly; do NOT auto-resolve.
            expected_key = _obligation_key(employee, week_label)
            if (legacy.get("obligation_key") or "") != expected_key:
                frappe.log_error(
                    "wr.anomaly mismatched obligation_key wtu=" + legacy["name"]
                    + " expected=" + expected_key
                    + " actual=" + (legacy.get("obligation_key") or "<empty>"),
                    "wr.anomaly",
                )
                return "skipped"
            # Same key tagged -> equivalent to reused.
            _ensure_todo(legacy["name"], user, week, due_at, now)
            return "reused"
        # Adopt: tag fields, ensure ToDo.
        doc = frappe.get_doc(WTU, legacy["name"])
        _set_obligation_fields(doc, schedule, week, due_at)
        doc.save(ignore_permissions=True)
        _ensure_todo(doc.name, user, week, due_at, now)
        return "adopted"

    # ---- 3. create new WTU Draft + ToDo ------------------------------------
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

    Order matters:
      1. assign_to.remove (native)  -> clears _assign, sets ToDo.status=Cancelled atomically
      2. reload ToDo                -> pick up the Cancelled state
      3. set status = "Closed"      -> semantic flip
      4. todo.save                   -> persists; ToDo.validate guard sees
                                       WTU.status=Submitted (caller ran on_weekly_update
                                       only because the just-saved WTU is Submitted)
                                       and lets the close through.

    Errors are NOT swallowed; we log + raise so the surrounding WTU save
    transaction can be rolled back by the framework and we never end up with a
    Submitted WTU but an Open obligation ToDo.
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
        return  # idempotent: nothing open to close

    from frappe.desk.form.assign_to import remove as _assign_remove
    for t in todos:
        user = t.get("allocated_to")
        if not user:
            # Defensive: ToDo without allocated_to cannot be removed via assign_to API.
            frappe.log_error(
                "wr.close ToDo " + t["name"] + " has no allocated_to; skipping",
                "wr.close",
            )
            continue
        try:
            _assign_remove(WTU, wtu_name, user)
            td = frappe.get_doc("ToDo", t["name"])
            td.status = "Closed"
            td.save(ignore_permissions=True)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "wr.close " + t["name"])
            raise
