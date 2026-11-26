# Copyright (c) 2026, eCentric and contributors
"""Ban quyen phan mem - phan tinh THUAN (khong DB): moc nhac han, giai doan, chi phi quy thang.

Quy tac nhac (Hoan 26/11/2026): truoc 30 ngay khi het han; goi ngan han (theo thang, hoac ky
khac dai <= 31 ngay) truoc 10 ngay. Ban quyen vinh vien khong co han -> khong nhac.
"""
import datetime as _dt

from ecentric_workspace.tai_san import constants as C


def _d(v):
    if not v:
        return None
    if isinstance(v, _dt.datetime):
        return v.date()
    if isinstance(v, _dt.date):
        return v
    return _dt.date.fromisoformat(str(v)[:10])


def term_days(lic):
    """Do dai ky hien tai (ngay): tu ngay gia han / bat dau gan nhat toi ngay het han."""
    start, end = _d(lic.get("current_term_start") or lic.get("start_date")), _d(lic.get("expiry_date"))
    if not (start and end):
        return None
    return (end - start).days


def is_short_term(lic):
    if lic.get("billing_cycle") == C.CY_MONTHLY:
        return True
    days = term_days(lic)
    return lic.get("billing_cycle") == C.CY_OTHER and days is not None and days <= C.SHORT_TERM_MAX_DAYS


def lead_days(lic):
    """So ngay bao truoc; None = khong nhac (vinh vien / khong co han)."""
    if lic.get("license_type") == C.LT_PERPETUAL or not lic.get("expiry_date"):
        return None
    return C.LICENSE_LEAD_DAYS_SHORT if is_short_term(lic) else C.LICENSE_LEAD_DAYS


def days_left(lic, today):
    exp = _d(lic.get("expiry_date"))
    return (exp - _d(today)).days if exp else None


def stage(lic, today):
    """OK / Due / Expired; None khi khong ap dung (vinh vien, da huy)."""
    if lic.get("status") == C.LS_CANCELLED:
        return None
    lead = lead_days(lic)
    if lead is None:
        return None
    left = days_left(lic, today)
    if left < 0:
        return C.STAGE_EXPIRED
    if left <= lead:
        return C.STAGE_DUE
    return C.STAGE_OK


def needs_alert(lic, today):
    """Giai doan can bao, hoac None neu da bao giai doan nay cho dung han nay roi.

    alert_stage + alert_for_expiry ghi lai lan bao gan nhat: gia han xong (han moi) thi moc reset
    tu nhien vi alert_for_expiry khong con bang han moi."""
    st = stage(lic, today)
    if st not in (C.STAGE_DUE, C.STAGE_EXPIRED):
        return None
    same_term = str(lic.get("alert_for_expiry") or "")[:10] == str(lic.get("expiry_date") or "")[:10]
    if same_term and lic.get("alert_stage") == st:
        return None
    return st


def cycle_months(lic):
    if lic.get("billing_cycle") in C.CYCLE_MONTHS:
        return C.CYCLE_MONTHS[lic["billing_cycle"]]
    days = term_days(lic)
    return max(1, round(days / 30.4)) if days else None


def monthly_cost(lic):
    """Chi phi quy ra thang cho thue bao dang dung; vinh vien = 0 (chi phi mot lan, xem tren phieu)."""
    if lic.get("license_type") != C.LT_SUBSCRIPTION or lic.get("status") != C.LS_ACTIVE:
        return 0.0      # het han / da huy: khong con ton tien moi thang
    months = cycle_months(lic)
    cost = float(lic.get("cost_per_cycle") or 0)
    return round(cost / months, 0) if months else 0.0


def next_expiry(lic):
    """Han moi goi y khi gia han dung mot ky (tu han cu, hoac hom nay neu da qua han lau)."""
    exp = _d(lic.get("expiry_date"))
    months = C.CYCLE_MONTHS.get(lic.get("billing_cycle"))
    if not (exp and months):
        return None
    y, m = exp.year, exp.month + months
    y, m = y + (m - 1) // 12, (m - 1) % 12 + 1
    last = [31, 29 if y % 4 == 0 and (y % 100 or y % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return _dt.date(y, m, min(exp.day, last))
