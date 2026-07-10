# Copyright (c) 2026, eCentric and contributors
"""Duration / age / aging-bucket helpers for Approval Center reporting.

Rules (locked):
- Average approval time = completed_at - submitted_at (fallback first-level activated_at,
  then creation); Draft & Cancelled excluded by the caller.
- Current pending age = now - active level activated_at (fallback request submitted_at,
  then creation).
- Aging buckets on age-in-days: <1d, 1-2d, 3-5d, >5d.
Returns are in seconds unless stated; formatting happens in the frontend.
"""
from frappe.utils import get_datetime, now_datetime

AGING_BUCKETS = ["<1d", "1-2d", "3-5d", ">5d"]


def _dt(v):
    return get_datetime(v) if v else None


def seconds_between(start, end):
    s, e = _dt(start), _dt(end)
    if not s or not e:
        return None
    return (e - s).total_seconds()


def approval_duration_seconds(row):
    """Completed duration for a finished request. row: submitted_at, completed_at,
    first_activated_at, creation. Returns seconds or None."""
    start = row.get("submitted_at") or row.get("first_activated_at") or row.get("creation")
    end = row.get("completed_at")
    return seconds_between(start, end)


def pending_age_seconds(row, ref_now=None):
    """Age of the currently-active level. row: current_activated_at, submitted_at, creation."""
    now = ref_now or now_datetime()
    start = row.get("current_activated_at") or row.get("submitted_at") or row.get("creation")
    return seconds_between(start, now)


def aging_bucket(age_seconds):
    if age_seconds is None:
        return None
    days = age_seconds / 86400.0
    if days < 1:
        return "<1d"
    if days < 3:
        return "1-2d"      # 1 up to <3 calendar days
    if days <= 5:
        return "3-5d"
    return ">5d"


def empty_bucket_counts():
    return {b: 0 for b in AGING_BUCKETS}
