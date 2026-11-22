# Copyright (c) 2026, eCentric and contributors
"""Kiem tra phap ly mot ho so (khong ghi gi): thoi hieu D123 (ke ca keo dai D123.2), thoi gian
khong duoc xu ly D122.4, tai pham. Dung chung cho moi buoc thu tuc + man hinh HR."""
import datetime as _dt

from ecentric_workspace.hr.ky_luat import constants as C
from ecentric_workspace.hr.ky_luat.application.common import int_setting
from ecentric_workspace.hr.ky_luat.domain import dates as D
from ecentric_workspace.hr.ky_luat.domain import rules as R


def block_periods(repo, case, until):
    """Moi khoang khong duoc xu ly da biet: nghi phep da duyet (tu dong) + khoang HR da ghi
    (tam giu, cho dieu tra, thai san...). -> [(tu, den, ly do)]."""
    v = D.as_date(case.get("violation_date"))
    out = []
    if v and case.get("employee"):
        for a, b in repo.leave_periods(case["employee"], v, until):
            out.append((a, b, C.BLOCK_LEAVE))
    for row in case.get("block_periods") or []:
        try:
            out.append((D.as_date(row[0]), D.as_date(row[1]), row[2] if len(row) > 2 else ""))
        except (TypeError, ValueError, IndexError):
            continue
    if case.get("block_reason") and case.get("block_from") and case.get("block_to"):
        out.append((D.as_date(case["block_from"]), D.as_date(case["block_to"]), case["block_reason"]))
    return [r for r in out if r[0] and r[1] and r[0] <= r[1]]


def assess(repo, case, on_day=None):
    """-> dict ket qua kiem. `on_day`: ngay can xet co vuong thoi gian cam khong (mac dinh hom nay)."""
    today = repo.today()
    on_day = D.as_date(on_day) or today
    v = D.as_date(case.get("violation_date"))
    out = {"today": str(today), "errors": [], "warnings": [], "blocked": None}
    if not v:
        out["errors"].append("Chưa có ngày vi phạm - không tính được thời hiệu.")
        return out
    finance = bool(int(case.get("finance_related") or 0))
    horizon = D.add_months(v, C.LIMITATION_MONTHS_FINANCE) + _dt.timedelta(days=400)
    periods = block_periods(repo, case, max(horizon, on_day))
    base, end, used = D.effective_limitation(v, finance, [(a, b) for a, b, _r in periods])
    out.update({"limitation_end": str(base), "limitation_effective_end": str(end),
                "limitation_months": D.limitation_months(finance),
                "extended_by": [[str(a), str(b)] for a, b in used],
                "days_left": D.days_left(end, today), "expired": D.is_expired(end, today)})
    if out["expired"]:
        out["errors"].append("Đã hết thời hiệu xử lý kỷ luật (Điều 123) từ %s - không được kỷ luật." % end)
    else:
        warn = int_setting(repo.settings(), "limitation_warn_days", C.DEFAULT_LIMITATION_WARN_DAYS)
        if out["days_left"] <= warn:
            out["warnings"].append("Còn %d ngày tới hết thời hiệu (%s)." % (out["days_left"], end))
    hit = None
    for a, b, reason in periods:
        if a <= on_day <= b:
            hit = {"from": str(a), "to": str(b), "reason": reason or C.BLOCK_LEAVE}
            break
    out["blocked"] = hit
    if hit:
        out["errors"].append("Ngày %s nhân viên đang trong thời gian không được xử lý kỷ luật "
                             "(Điều 122.4: %s, %s - %s) - phải hoãn." % (on_day, hit["reason"], hit["from"], hit["to"]))
    prior = [r for r in repo.cases_of_employee(case.get("employee"), (C.S_ISSUED,))
             if r.get("name") != case.get("name")] if case.get("employee") else []
    out["recidivism_note"] = R.recidivism_note(prior, today)
    out["prior_cases"] = prior
    return out
