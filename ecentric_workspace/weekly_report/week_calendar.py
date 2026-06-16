# Copyright (c) 2026, eCentric and contributors
"""Week calendar helpers.

Port of the JS function `calculateCurrentWeek()` in Web Page
`/weekly-update` (snapshot 06_wp_weekly_update_full.json, lines ~1060-1100).
ANY DIVERGENCE from that JS function = scheduler vs UI drift; tests in
test_week_calendar.py assert parity on the edge cases that drove the UI logic
(Friday 18:00 rollover, year-boundary).

Also exposes compute_due_at(): looks up the Department Reporting Window for a
department and returns the deadline as a Datetime. The lookup mirrors
`weekly_late_detector` (production Server Script, snapshot
04_src_weekly_late_detector.json): DRW.name == Department.name (autoname
field:department, verified in snapshot 01_doctype_drw_full.json), fields
[deadline_day, deadline_time, deadline_in_next_week, enabled]. Hotfix:
we DO filter on `enabled`. Production late-detector parity was relevant when
the scheduler was Schedule-driven; the Employee-driven hotfix requires admin
to be able to disable a Department's window without rewriting it, so the
scheduler skips disabled DRW. Late-detector remains unchanged in prod
(separate code path, separate concern).
"""

from datetime import datetime, timedelta, date, time as _time

import frappe


class MissingReportingWindowError(Exception):
    """Raised when DRW is missing/incomplete for a department.

    Callers (ensure_weekly_obligation) MUST catch and skip + log; never fall
    back to a hard-coded default deadline.
    """


def _pad2(n):
    return ("0" if n < 10 else "") + str(n)


def _now(now=None):
    """Normalize `now` -> datetime in site timezone.

    Supported inputs:
      * None        -> frappe.utils.now_datetime() (site tz)
      * str         -> frappe.utils.get_datetime(str)  (ISO date or datetime)
      * datetime    -> as-is
      * date        -> datetime.combine(value, time.min) (midnight)
    """
    if now is None:
        return frappe.utils.now_datetime()
    if isinstance(now, str):
        return frappe.utils.get_datetime(now)
    if isinstance(now, datetime):
        return now
    if isinstance(now, date):
        return datetime.combine(now, _time.min)
    raise TypeError("Unsupported `now` type: " + str(type(now)))


def compute_week_for(now=None):
    """Port of calculateCurrentWeek() (JS, /weekly-update).

    Returns dict with keys:
      week_label        - "YYYY-Www" (ISO 8601 week, zero-padded)
      week_start_date   - datetime.date (Monday)
      week_end_date     - datetime.date (Friday)  -- UI semantic, NOT Sunday
      default_deadline  - datetime (Friday 18:00) -- UI fallback; DRW overrides
    """
    cur = _now(now)
    today = cur.replace(hour=0, minute=0, second=0, microsecond=0)
    # JS: (today.getDay()+6) % 7 maps Sun=0..Sat=6 to Mon=0..Sun=6.
    # Python: weekday() already returns Mon=0..Sun=6.
    weekday_mon0 = today.weekday()
    monday = today - timedelta(days=weekday_mon0)
    friday = monday + timedelta(days=4)
    deadline = friday.replace(hour=18, minute=0, second=0, microsecond=0)
    # JS: "if (now > deadline && weekday_mon0 >= 4) roll forward 7 days".
    if cur > deadline and weekday_mon0 >= 4:
        monday += timedelta(days=7)
        friday += timedelta(days=7)
        deadline += timedelta(days=7)
    # ISO week via Thursday rule (matches JS line ~1077-1082 exactly).
    thursday = monday + timedelta(days=3)
    iso_year, iso_week, _iso_dow = thursday.isocalendar()
    return {
        "week_label": "%04d-W%02d" % (iso_year, iso_week),
        "week_start_date": monday.date(),
        "week_end_date": friday.date(),
        "default_deadline": deadline,
    }


def compute_due_at(week, department):
    """Return deadline datetime for a given week + department, using DRW.

    Raises MissingReportingWindowError if the DRW is missing or incomplete.
    No silent fallback. Caller must catch and skip the schedule with a logged
    error.

    Mirrors weekly_late_detector lookup pattern verified in snapshot:
      frappe.db.exists("Department Reporting Window", department)
      frappe.db.get_value("Department Reporting Window", department,
        ["deadline_day", "deadline_time", "deadline_in_next_week", "enabled"], as_dict=True)

    department here MUST be the Department record name (DRW autoname is
    field:department, so DRW.name == Department.name).
    """
    if not department:
        raise MissingReportingWindowError("department is empty")
    if not frappe.db.exists("Department Reporting Window", department):
        raise MissingReportingWindowError(
            "Department Reporting Window not found for department: " + str(department)
        )
    w = frappe.db.get_value(
        "Department Reporting Window",
        department,
        ["deadline_day", "deadline_time", "deadline_in_next_week"],
        as_dict=True,
    )
    if not w:
        raise MissingReportingWindowError(
            "Department Reporting Window row exists but get_value returned no data for: "
            + str(department)
        )
    # Hotfix: enforce DRW.enabled=1 (production parity dropped; an explicit
    # disable on DRW must skip the schedule, not silently still generate).
    if not w.get("enabled"):
        raise MissingReportingWindowError(
            "Department Reporting Window disabled for: " + str(department)
        )
    deadline_day = w.get("deadline_day")
    if not deadline_day:
        raise MissingReportingWindowError(
            "deadline_day empty on Department Reporting Window for: " + str(department)
        )
    deadline_time_raw = w.get("deadline_time")
    if deadline_time_raw is None:
        raise MissingReportingWindowError(
            "deadline_time empty on Department Reporting Window for: " + str(department)
        )

    # Day map mirrors weekly_late_detector (Monday=1..Sunday=7).
    day_map = {
        "Monday": 1, "Tuesday": 2, "Wednesday": 3, "Thursday": 4,
        "Friday": 5, "Saturday": 6, "Sunday": 7,
    }
    deadline_num = day_map.get(deadline_day)
    if deadline_num is None:
        raise MissingReportingWindowError(
            "Unknown deadline_day value '" + str(deadline_day) + "' for: " + str(department)
        )
    days_offset = deadline_num - 1  # days after week_start (Monday)
    if w.get("deadline_in_next_week"):
        days_offset += 7

    # week["week_start_date"] is a datetime.date.
    deadline_date = week["week_start_date"] + timedelta(days=days_offset)
    # Time field round-trips as string ("HH:MM:SS"), Python datetime.time, or
    # datetime.timedelta depending on driver; str() + get_datetime() handles
    # all three (verified by weekly_late_detector running in production).
    deadline_str = str(deadline_date) + " " + str(deadline_time_raw)
    return frappe.utils.get_datetime(deadline_str)
