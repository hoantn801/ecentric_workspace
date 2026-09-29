# Copyright (c) 2026, eCentric and contributors
"""Chot cong thang - phan THUAN (khong import frappe), kiem chung bang python tran.

QUY TAC (Hoan chot 29/09/2026, xem project doc claude/chot-cong-thang.md)
    Cong thang M chot vao NGAY 2 thang M+1:
        - nhan vien tu chot truoc 12:00,
        - leader (quan ly truc tiep) chot ca team truoc 15:00 CUNG NGAY.
    Ngay 2 roi vao T7/CN hoac ngay le (lich nghi cong ty) -> CA HAI moc doi sang ngay
    lam viec ke tiep. Tre nhat la thu 2 ngay 4.
    Nhan vien tre -> leader chot thay khi chot team, nhan vien van bi tinh tre.
    Leader chi chot duoc khi da xu ly het viec DANG CHO CHINH HO duyet.
    Nguoi khong co quan ly (CEO...) -> CnB / HR chot thay.
"""
import datetime as _dt

# Ky dau tien ap dung: cong thang 9/2026 (han T6 02/10/2026). Ky truoc do KHONG
# sinh ban ghi, KHONG khoa - tranh khoa hoi to nhung thang da tra luong.
START_PERIOD = "2026-09"
MEMBER_HOUR = 12
LEAD_HOUR = 15
CLOSE_DAY = 2

ST_OPEN = "Open"
ST_MEMBER = "Member Closed"
ST_CLOSED = "Closed"
LOCKED_STATES = (ST_MEMBER, ST_CLOSED)

MODE_SELF = "Tu chot"
MODE_LEAD = "Leader chot thay"
MODE_HR = "HR chot thay"


def _d(x):
    if isinstance(x, _dt.datetime):
        return x.date()
    if isinstance(x, _dt.date):
        return x
    return _dt.date.fromisoformat(str(x)[:10])


def period_of(day):
    """Ngay -> 'YYYY-MM'."""
    return _d(day).strftime("%Y-%m")


def period_bounds(period):
    """'YYYY-MM' -> (ngay dau, ngay cuoi) cua thang."""
    y, m = int(period[:4]), int(period[5:7])
    first = _dt.date(y, m, 1)
    nxt = _dt.date(y + (m == 12), m % 12 + 1, 1)
    return first, nxt - _dt.timedelta(days=1)


def next_period_first_day(period):
    return period_bounds(period)[1] + _dt.timedelta(days=1)


def prev_period(day):
    """Ky dang chot tinh tu mot ngay: luon la thang TRUOC."""
    first = _d(day).replace(day=1)
    return period_of(first - _dt.timedelta(days=1))


def close_date(period, holidays=()):
    """Ngay chot cua ky: ngay 2 thang sau, doi qua T7/CN/ngay le."""
    hol = {_d(h) for h in holidays}
    d = next_period_first_day(period).replace(day=CLOSE_DAY)
    while d.weekday() >= 5 or d in hol:
        d += _dt.timedelta(days=1)
    return d


def deadlines(period, holidays=()):
    """(han nhan vien, han leader) dang datetime (gio site)."""
    d = close_date(period, holidays)
    return (_dt.datetime.combine(d, _dt.time(MEMBER_HOUR, 0)),
            _dt.datetime.combine(d, _dt.time(LEAD_HOUR, 0)))


def applies(period):
    return bool(period) and period >= START_PERIOD


def window_open(period, now):
    """Nut chot hien tu 00:00 ngay 1 thang sau."""
    return applies(period) and _d(now) >= next_period_first_day(period)


def on_time(closed_at, due):
    return closed_at is not None and closed_at <= due
