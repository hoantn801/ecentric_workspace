# Copyright (c) 2026, eCentric and contributors
"""Fill in `due_at` on Weekly Team Update rows that were born without one.

WHY THESE ROWS EXIST: two code paths create a WTU. The daily generator
(service.ensure_weekly_obligation) always sets a deadline; the submit path
(submit_service._get_or_create) did not, until 2026-09-18. Anyone submitting
before the generator ran for their week got a row with no deadline, which
_apply_fields() then marked Submitted, after which the generator skipped it
forever (`status in TERMINAL_STATES`). 211 such rows on the 2026-09-17 scan.

WHY A ONE-OFF SERVICE AND NOT A CRON: the alternative proposed was to let
ensure_weekly_obligation repair Submitted rows. That means widening
TERMINAL_STATES, which exists to stop the generator writing into reports people
have already filed. Opening a write path into closed records, every night, to
fix a bug that lives elsewhere, is a worse trade than one reviewable pass.

TWO THINGS THE CALLER MUST UNDERSTAND
1. There is no history of reporting windows. compute_due_at() reads the DRW as
   it stands today, so filling a closed week asserts the department's deadline
   never changed. For recent weeks that is usually true; the further back you
   go the less true it gets.
2. Giving a row a deadline can make its author LATE. Right now these rows are
   unmeasurable, so nobody is late. Some of them WILL be late once measured --
   and not through any fault of the author, since the missing deadline was our
   bug. `would_be_late` in the report is that number. Look at it before writing.

Public API:
  preview(weeks=None, limit=500)            -> dict   (never writes)
  backfill(weeks=None, limit=500,
           dry_run=True, skip_if_late=False) -> dict
"""

import frappe

from ecentric_workspace.weekly_report import week_calendar

WTU = "Weekly Team Update"


def _rows(weeks, limit):
    """Rows with no deadline. `weeks` None = every week (report only, please)."""
    filters = {"due_at": ("is", "not set")}
    if weeks:
        filters["week_label"] = ("in", list(weeks))
    return frappe.get_all(
        WTU,
        filters=filters,
        fields=[
            "name", "employee", "week_label", "department",
            "status", "submitted_at", "obligation_key",
        ],
        order_by="week_label asc, name asc",
        limit_page_length=limit,
    )


def _plan_one(row):
    """Work out what this row should get. Pure -- no writes, no exceptions out.

    Returns a dict with `action` in:
      fill        -> due_at computed, author was on time (or never submitted)
      fill_late   -> due_at computed, but submitted_at is AFTER it
      no_window   -> DRW missing/disabled, or the label is malformed
    """
    name = row.get("name")
    employee = row.get("employee")
    week_label = row.get("week_label")

    # Department from the Employee record: compute_due_at needs the Department
    # record name, and WTU.department is a display string written by the form.
    department = (
        frappe.db.get_value("Employee", employee, "department") if employee else None
    )

    out = {
        "name": name,
        "employee": employee,
        "week_label": week_label,
        "department": department,
        "submitted_at": row.get("submitted_at"),
        "obligation_key": row.get("obligation_key") or "",
        "due_at": None,
        "action": "no_window",
        "reason": "",
    }

    try:
        due_at = week_calendar.due_at_for_label(week_label, department)
    except (week_calendar.MissingReportingWindowError, ValueError) as exc:
        out["reason"] = str(exc)[:200]
        return out

    out["due_at"] = due_at
    submitted_at = row.get("submitted_at")
    if submitted_at and due_at and frappe.utils.get_datetime(submitted_at) > due_at:
        out["action"] = "fill_late"
    else:
        out["action"] = "fill"
    return out


def _empty_report(weeks, limit, dry_run, skip_if_late):
    return {
        "weeks": list(weeks) if weeks else "all",
        "limit": limit,
        "dry_run": bool(dry_run),
        "skip_if_late": bool(skip_if_late),
        "scanned": 0,
        "would_fill": 0,
        "would_be_late": 0,
        "no_window": 0,
        "written": 0,
        "skipped_late": 0,
        "write_errors": 0,
        "no_window_rows": [],
        "late_rows": [],
        "errors": [],
    }


def _apply(plan, report):
    """Write one row. Only ever called with dry_run False."""
    try:
        doc = frappe.get_doc(WTU, plan["name"])
        doc.due_at = plan["due_at"]
        if not (doc.obligation_key or "").strip():
            doc.obligation_key = str(plan["employee"]) + "::" + str(plan["week_label"])
        # generated_obligation is left alone: the generator did not create this
        # row and the flag must keep telling the truth about that.
        doc.save(ignore_permissions=True)
        report["written"] = report["written"] + 1
    except Exception as exc:
        report["write_errors"] = report["write_errors"] + 1
        report["errors"].append(str(plan["name"]) + ": " + str(exc)[:160])


def preview(weeks=None, limit=500):
    """Report what backfill() would do. Writes nothing, ever."""
    return backfill(weeks=weeks, limit=limit, dry_run=True)


def backfill(weeks=None, limit=500, dry_run=True, skip_if_late=False):
    """Fill missing `due_at`.

    weeks        list of week_label, e.g. ["2026-W38"]. None scans every week --
                 fine for a preview, but think hard before writing that wide.
    dry_run      True (default) reports and writes nothing.
    skip_if_late True leaves rows alone when the author would come out late, so
                 a bug of ours cannot cost somebody their SLA number.
    """
    report = _empty_report(weeks, limit, dry_run, skip_if_late)

    for row in _rows(weeks, limit):
        report["scanned"] = report["scanned"] + 1
        plan = _plan_one(row)

        if plan["action"] == "no_window":
            report["no_window"] = report["no_window"] + 1
            if len(report["no_window_rows"]) < 40:
                report["no_window_rows"].append({
                    "name": plan["name"],
                    "week_label": plan["week_label"],
                    "department": plan["department"],
                    "reason": plan["reason"],
                })
            continue

        report["would_fill"] = report["would_fill"] + 1
        if plan["action"] == "fill_late":
            report["would_be_late"] = report["would_be_late"] + 1
            if len(report["late_rows"]) < 40:
                report["late_rows"].append({
                    "name": plan["name"],
                    "week_label": plan["week_label"],
                    "due_at": str(plan["due_at"]),
                    "submitted_at": str(plan["submitted_at"]),
                })
            if skip_if_late:
                report["skipped_late"] = report["skipped_late"] + 1
                continue

        if not dry_run:
            _apply(plan, report)

    return report
