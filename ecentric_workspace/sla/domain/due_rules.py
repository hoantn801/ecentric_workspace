# Copyright (c) 2026, eCentric and contributors
"""Tinh HAN cua mot nghia vu. Thuan - khong import frappe, chay duoc bang python3 tran.

Bon luat, moi luat mot cach doi tu "luc mo" sang "han chot":

  Business Hours   han = mo + N gio LAM VIEC (bo cuoi tuan, le, nghi trua).
                   Dung cho buoc phe duyet: dat don 17h thu Sau, SLA 4 gio, thi
                   han roi vao sang thu Hai - chu khong phai 21h thu Sau.
  Calendar Hours   han = mo + N gio dong ho. Dung cho viec khong phan biet gio
                   hanh chinh (vd RSVP: loi moi gui toi van phai tra loi).
  Fixed Time Of Day  han = mot gio co dinh cua ngay (+/- so ngay lech). Dung cho
                   cham cong: han check-in = dau ca + an han, han check-out = 23:59.
  Explicit         nguon tu dua `due_at` vao. Module SLA khong tinh lai.

Phep tinh gio lam viec KHONG viet lai o day. No da ton tai va da chay tren ban
song trong `approval_center/shared/workflow/business_hours.py`. File nay chi goi
sang. Viet ban thu hai se tao ra hai dinh nghia "gio lam viec" trong cung mot he
- dung loai loi da tung xay ra voi %SLA cu (mot cong thuc trong Power BI, mot
cong thuc trong dau nguoi doc).
"""
from datetime import datetime, timedelta, time

from ecentric_workspace.sla.constants import (
    DUE_BUSINESS_HOURS, DUE_CALENDAR_HOURS, DUE_EXPLICIT, DUE_FIXED_TIME,
)


class DueRuleError(ValueError):
    """Cau hinh luat han khong dung - nem ra de nguoi cau hinh thay ngay,
    thay vi tra ve None roi de nghia vu khong bao gio den han."""


def _as_naive(dt):
    """Frappe luu datetime naive theo mui gio he thong. Chuan hoa moi dau vao ve
    dang do; giu nguyen thi phep tru datetime se no TypeError o cho khac."""
    if dt is None:
        return None
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt.replace("Z", ""))
    if isinstance(dt, datetime) and dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    return dt


def _coerce_time(v):
    if v is None:
        return None
    if isinstance(v, time):
        return v
    if isinstance(v, timedelta):
        s = int(v.total_seconds())
        return time((s // 3600) % 24, (s // 60) % 60, s % 60)
    if isinstance(v, datetime):
        return v.time()
    if isinstance(v, str):
        p = (v.split(" ")[-1]).split(":")
        return time(int(p[0]), int(p[1]) if len(p) > 1 else 0,
                    int(float(p[2])) if len(p) > 2 else 0)
    raise DueRuleError("gia tri gio khong ho tro: %r" % (v,))


def resolve_due(rule, opened_at, duration_hours=None, fixed_time=None,
                offset_days=0, grace_minutes=0, explicit_due=None,
                business_due_fn=None):
    """Tra ve datetime naive la HAN cua nghia vu.

    `business_due_fn(start_dt, duration_hours) -> datetime` la cong duy nhat di
    ra ngoai: nguoi goi bom vao ham gio-lam-viec cua approval_center. Tiem no
    qua tham so (chu khong import thang) giu file nay thuan va test duoc khong
    can bench - va cung la cach duy nhat de test mot lich lam viec gia dinh.

    `grace_minutes` cong vao SAU cung, ke ca voi gio lam viec. Co y: an han la
    khoan khoan dung theo dong ho that (5 phut la 5 phut), khong phai 5 phut lam
    viec - neu tinh theo gio lam viec thi an han dat luc 17h59 se nhay sang
    8h04 hom sau, tuc la an han mot dem.
    """
    opened_at = _as_naive(opened_at)

    if rule == DUE_EXPLICIT:
        due = _as_naive(explicit_due)
        if due is None:
            raise DueRuleError("luat Explicit yeu cau explicit_due")
        return due + timedelta(minutes=grace_minutes or 0)

    if rule == DUE_FIXED_TIME:
        t = _coerce_time(fixed_time)
        if t is None:
            raise DueRuleError("luat Fixed Time Of Day yeu cau fixed_time")
        if opened_at is None:
            raise DueRuleError("luat Fixed Time Of Day yeu cau opened_at")
        base = datetime.combine(opened_at.date() + timedelta(days=int(offset_days or 0)), t)
        return base + timedelta(minutes=grace_minutes or 0)

    if opened_at is None:
        raise DueRuleError("luat %s yeu cau opened_at" % rule)
    if not duration_hours or float(duration_hours) <= 0:
        raise DueRuleError("luat %s yeu cau duration_hours > 0" % rule)

    if rule == DUE_CALENDAR_HOURS:
        return opened_at + timedelta(hours=float(duration_hours),
                                     minutes=grace_minutes or 0)

    if rule == DUE_BUSINESS_HOURS:
        if business_due_fn is None:
            raise DueRuleError("luat Business Hours yeu cau business_due_fn")
        due = _as_naive(business_due_fn(opened_at, float(duration_hours)))
        if due is None:
            raise DueRuleError("business_due_fn khong tra ve han")
        return due + timedelta(minutes=grace_minutes or 0)

    raise DueRuleError("luat han khong hop le: %r" % (rule,))


def period_of(dt, period_format="%Y-%m"):
    """Khoa ky cham diem cua mot moc thoi gian: "2026-09".

    Ky duoc chot theo LUC MO, khong theo luc dong. Mot buoc duyet mo ngay 30/9
    va duyet ngay 2/10 van thuoc ky thang 9 - noi no phat sinh. Chot theo luc
    dong se cho phep day viec tre sang thang sau de lam sach thang nay.
    """
    dt = _as_naive(dt)
    if dt is None:
        return None
    return dt.strftime(period_format)


def period_bounds(period, period_format="%Y-%m"):
    """("2026-09") -> (datetime(2026,9,1,0,0), datetime(2026,10,1,0,0)) - nua mo [dau, cuoi)."""
    start = datetime.strptime(period, period_format)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end
