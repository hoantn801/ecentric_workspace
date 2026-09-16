# Copyright (c) 2026, eCentric and contributors
"""Reusable business-hours SLA calculator (pure; unit-testable).

Works on naive datetimes in the site/system timezone (Frappe stores naive
system-tz datetimes). Processes whole working intervals - no minute iteration.
Excludes weekends (days with no configured period), Holiday List dates, lunch,
and any time outside configured periods; rolls forward to the next valid instant.
"""
import datetime as _dt
from datetime import datetime, timedelta, time

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
WD_INDEX = {w: i for i, w in enumerate(WEEKDAYS)}


def _to_time(v):
    if isinstance(v, time):
        return v
    if isinstance(v, timedelta):
        s = int(v.total_seconds())
        return time((s // 3600) % 24, (s // 60) % 60, s % 60)
    if isinstance(v, datetime):
        return v.time()
    if isinstance(v, str):
        p = (v.split(" ")[-1]).split(":")
        return time(int(p[0]), int(p[1]) if len(p) > 1 else 0, int(float(p[2])) if len(p) > 2 else 0)
    raise ValueError("unsupported time value: %r" % (v,))


def _as_naive(dt):
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    if isinstance(dt, datetime) and dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    return dt


def build_periods(working_periods):
    """rows with .weekday (name), .start_time, .end_time -> {weekday_int: [(time,time),...] sorted}."""
    out = {}
    for r in working_periods:
        wd = r.get("weekday") if isinstance(r, dict) else r.weekday
        st = _to_time(r.get("start_time") if isinstance(r, dict) else r.start_time)
        et = _to_time(r.get("end_time") if isinstance(r, dict) else r.end_time)
        out.setdefault(WD_INDEX[wd], []).append((st, et))
    for wd in out:
        out[wd].sort()
    return out


def calculate_business_due_at(start_dt, duration_hours, periods_by_wd, holidays=None, max_days=400):
    """start_dt naive datetime; duration_hours>0; periods_by_wd from build_periods;
    holidays = set of date objects. Returns the naive datetime when the work is due."""
    if not duration_hours or float(duration_hours) <= 0:
        raise ValueError("duration_hours must be positive")
    start_dt = _as_naive(start_dt)
    holidays = holidays or set()
    remaining = float(duration_hours) * 3600.0
    cursor = start_dt
    for _ in range(max_days + 1):
        d = cursor.date()
        if d in holidays or not periods_by_wd.get(d.weekday()):
            cursor = datetime.combine(d + timedelta(days=1), time(0, 0))
            continue
        for st, et in periods_by_wd[d.weekday()]:
            istart, iend = datetime.combine(d, st), datetime.combine(d, et)
            if cursor >= iend:
                continue
            if cursor < istart:
                cursor = istart
            avail = (iend - cursor).total_seconds()
            if remaining <= avail:
                return cursor + timedelta(seconds=remaining)
            remaining -= avail
            cursor = iend
        cursor = datetime.combine(d + timedelta(days=1), time(0, 0))
    raise ValueError("Business due date not resolvable within %d days (empty/invalid calendar?)" % max_days)

def business_seconds_between(start_dt, end_dt, periods_by_wd, holidays=None, max_days=400):
    """So GIAY LAM VIEC giua hai moc. Nguoc chieu voi calculate_business_due_at.

    Can cho SLA: "tre bao lau" phai do bang cung thuoc do voi "han bao lau".
    Mot buoc duyet han 4 gio lam viec, dat luc 16h thu Sau, duyet luc 9h thu Hai
    thi tre 1 gio lam viec - khong phai 65 gio dong ho. Do bang dong ho se bien
    moi cuoi tuan thanh mot vu tre nghiem trong va lam ca bang xep hang vo nghia.

    Tra ve 0 khi end <= start. Khong nem loi khi lich rong: tra ve 0 - do la con
    so an toan (khong buoc toi ai) trong khi calculate_business_due_at nem loi vi
    o do lich rong nghia la khong bao gio den han, mot trang thai khong the nuot.
    """
    start_dt, end_dt = _as_naive(start_dt), _as_naive(end_dt)
    if not start_dt or not end_dt or end_dt <= start_dt:
        return 0
    holidays = holidays or set()
    total = 0.0
    cursor = start_dt
    for _ in range(max_days + 1):
        if cursor >= end_dt:
            return int(total)
        d = cursor.date()
        if d in holidays or not periods_by_wd.get(d.weekday()):
            cursor = datetime.combine(d + timedelta(days=1), time(0, 0))
            continue
        for st, et in periods_by_wd[d.weekday()]:
            istart, iend = datetime.combine(d, st), datetime.combine(d, et)
            if cursor >= iend:
                continue
            if cursor < istart:
                cursor = istart
            stop = min(iend, end_dt)
            if stop > cursor:
                total += (stop - cursor).total_seconds()
            cursor = iend
            if cursor >= end_dt:
                return int(total)
        cursor = datetime.combine(d + timedelta(days=1), time(0, 0))
    return int(total)
