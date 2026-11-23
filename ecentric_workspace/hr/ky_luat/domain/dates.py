# Copyright (c) 2026, eCentric and contributors
"""Tinh ngay cua thu tuc ky luat - HAM THUAN (khong doc DB): ngay le truyen vao.

  * Thoi hieu D123.1: 6 thang tu ngay vi pham; 12 thang neu lien quan tai chinh, tai san, bi mat.
  * Keo dai D123.2: het thoi gian khong duoc xu ly (D122.4) ma thoi hieu da het hoac con duoi
    60 ngay -> keo dai, khong qua 60 ngay ke tu ngay het thoi gian do.
  * Ngay hop som nhat: ngay lam viec thu N SAU ngay thong bao (N = 5, Settings).
  * Han phan hoi the vang: ngay lam viec thu N sau ngay gui (N = 3, Settings).
  * Xoa ky luat D126: khien trach 3 thang, keo dai nang luong 6 thang, cach chuc 3 nam ke tu
    ngay bi xu ly. Sa thai: khong co ngay xoa.

"Ngay lam viec" = khong phai T7/CN va khong nam trong ngay le cong ty (ngay_lam_viec.py - mot
nguon cho ca he thong; khong xet lich nghi rieng cua tung nguoi).
"""
import calendar
import datetime as _dt

from ecentric_workspace.approval_center.shared.workflow.ngay_lam_viec import (
    cong_ngay_lam_viec, dem_ngay_lam_viec)
from ecentric_workspace.hr.ky_luat import constants as C

ONE_DAY = _dt.timedelta(days=1)


def as_date(v):
    """date | datetime | 'YYYY-MM-DD[...]' | None -> date | None."""
    if v is None or v == "":
        return None
    if isinstance(v, _dt.datetime):
        return v.date()
    if isinstance(v, _dt.date):
        return v
    return _dt.date.fromisoformat(str(v)[:10])


def add_months(d, months):
    """Cong thang theo lich, ngay vuot cuoi thang thi lay ngay cuoi thang (31/08 + 6 = 28|29/02)."""
    d = as_date(d)
    total = d.month - 1 + int(months)
    year, month = d.year + total // 12, total % 12 + 1
    return _dt.date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def limitation_months(finance_related):
    return C.LIMITATION_MONTHS_FINANCE if finance_related else C.LIMITATION_MONTHS


def limitation_end(violation_date, finance_related):
    """Ngay CUOI CUNG con duoc ban hanh quyet dinh (D123.1)."""
    return add_months(violation_date, limitation_months(finance_related))


def merge_periods(periods):
    """[(tu, den)] -> cac khoang KHONG chong nhau, sap theo ngay bat dau. Khoang lien ke (den + 1
    = tu ke tiep) cung gop: NV nghi lien hai don thi la mot thoi gian khong duoc xu ly."""
    rows = sorted((as_date(a), as_date(b)) for a, b in periods or () if a and b and as_date(a) <= as_date(b))
    out = []
    for a, b in rows:
        if out and a <= out[-1][1] + ONE_DAY:
            if b > out[-1][1]:
                out[-1] = (out[-1][0], b)
        else:
            out.append((a, b))
    return out


def extend_for_block(end, block_end):
    """D123.2 cho MOT khoang khong duoc xu ly ket thuc ngay `block_end`.

    Ngay duoc xu ly lai dau tien la block_end + 1. Neu luc do thoi hieu da het hoac con duoi 60
    ngay -> han moi = block_end + 60 ngay (toi da luat cho). Con du 60 ngay -> giu nguyen."""
    end, block_end = as_date(end), as_date(block_end)
    resume = block_end + ONE_DAY
    if (end - resume).days + 1 < C.EXTENSION_DAYS:
        return max(end, block_end + _dt.timedelta(days=C.EXTENSION_DAYS))
    return end


def effective_limitation(violation_date, finance_related, block_periods=()):
    """-> (han goc, han hieu luc, [khoang da lam keo dai]). Chi khoang bat dau truoc han dang
    tinh moi anh huong (khoang sau khi da het han thi thoi hieu het tu truoc, khong hoi sinh)."""
    base = limitation_end(violation_date, finance_related)
    end, used = base, []
    v = as_date(violation_date)
    for a, b in merge_periods(block_periods):
        if b < v or a > end:
            continue
        new_end = extend_for_block(end, b)
        if new_end != end:
            used.append((a, b))
        end = new_end
    return base, end, used


def days_left(end, today):
    """So ngay lich con lai TINH CA hom nay toi han (han = hom nay -> 1; qua han -> <= 0)."""
    return (as_date(end) - as_date(today)).days + 1


def is_expired(end, today):
    return as_date(today) > as_date(end)


def block_covering(day, periods):
    """Khoang khong duoc xu ly chua `day`, hoac None."""
    d = as_date(day)
    for a, b in merge_periods(periods):
        if a <= d <= b:
            return (a, b)
    return None


def workday_after(start, n, holidays=()):
    return cong_ngay_lam_viec(as_date(start), int(n), holidays)


def earliest_meeting(notice_date, notice_days, holidays=()):
    """Ngay hop som nhat: ngay lam viec thu `notice_days` sau ngay thong bao."""
    return workday_after(notice_date, notice_days, holidays)


def workdays_between(a, b, holidays=()):
    return dem_ngay_lam_viec(as_date(a), as_date(b), holidays)


def reply_due(sent_date, reply_days, holidays=()):
    """Han phan hoi the vang: het ngay lam viec thu `reply_days` sau ngay gui."""
    return workday_after(sent_date, reply_days, holidays)


def expunge_due(decision_date, penalty):
    """D126 - None neu hinh thuc khong duoc xoa (sa thai)."""
    months = C.EXPUNGE_MONTHS.get(penalty)
    return add_months(decision_date, months) if months else None
