# Copyright (c) 2026, eCentric and contributors
"""Time-series, percentile and period-comparison helpers for Approval Center reporting.

Pure computation over already-fetched, already-scoped rows (no DB access here).
"""
from collections import OrderedDict

from frappe.utils import get_datetime, add_to_date, date_diff


# ---------- percentiles ----------
def percentile(values, p):
    """Nearest-rank percentile (p in 0..100). Returns None for empty input."""
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    if p <= 0:
        return vals[0]
    if p >= 100:
        return vals[-1]
    import math
    k = max(1, int(math.ceil(p / 100.0 * len(vals))))
    return vals[k - 1]


def median(values):
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    n = len(vals)
    mid = n // 2
    return vals[mid] if n % 2 else (vals[mid - 1] + vals[mid]) / 2.0


# ---------- period comparison ----------
def previous_window(date_from, date_to):
    """The equivalent-length window immediately before [date_from, date_to]."""
    df, dt = get_datetime(date_from), get_datetime(date_to)
    days = max(1, date_diff(dt, df) + 1)
    prev_to = add_to_date(df, seconds=-1)
    prev_from = add_to_date(df, days=-days)
    return (str(prev_from), str(prev_to))


def delta(current, previous):
    """Absolute + percentage delta + direction. Handles None/0 safely."""
    cur = current or 0
    prev = previous or 0
    d = cur - prev
    if prev == 0:
        pct = None if cur == 0 else 100.0
    else:
        pct = round(d * 100.0 / prev, 1)
    direction = "flat" if d == 0 else ("up" if d > 0 else "down")
    return {"current": current, "previous": previous, "delta": d, "pct": pct, "direction": direction}


# ---------- time-series bucketing ----------
def granularity_for(date_from, date_to):
    days = date_diff(get_datetime(date_to), get_datetime(date_from)) + 1
    return "day" if days <= 31 else "week"


def _bucket_key(dt, granularity):
    d = get_datetime(dt)
    if granularity == "week":
        iso = d.isocalendar()
        return "%04d-W%02d" % (iso[0], iso[1])
    return d.strftime("%Y-%m-%d")


def build_time_buckets(rows, date_from, date_to, granularity, date_field="submitted_at"):
    """Group rows by submission bucket; each bucket carries total + per-status counts.
    'pending/completed/rejected' are the CURRENT status of requests submitted in that
    bucket (submission-cohort view - documented approximation, not a historical snapshot)."""
    buckets = OrderedDict()
    # pre-seed empty buckets so the line has no gaps
    cur = get_datetime(date_from)
    end = get_datetime(date_to)
    step_days = 7 if granularity == "week" else 1
    guard = 0
    while cur <= end and guard < 400:
        buckets[_bucket_key(cur, granularity)] = {"label": _bucket_key(cur, granularity),
                                                  "total": 0, "completed": 0, "pending": 0, "rejected": 0}
        cur = add_to_date(cur, days=step_days)
        guard += 1
    for r in rows:
        ref = r.get(date_field) or r.get("creation")
        if not ref:
            continue
        k = _bucket_key(ref, granularity)
        b = buckets.get(k)
        if not b:
            continue
        b["total"] += 1
        st = r.get("approval_status")
        if st == "Approved":
            b["completed"] += 1
        elif st in ("Pending", "Information Required"):
            b["pending"] += 1
        elif st in ("Rejected", "Cancelled"):
            b["rejected"] += 1
    return list(buckets.values())
