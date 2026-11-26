# Copyright (c) 2026, eCentric and contributors
"""So lieu Tong quan - ham THUAN tren danh sach Asset (khong import frappe, test khong can bench).

"Thiet bi" tren Tong quan = may khong phai linh kien dang lap (linh kien dem rieng), tru Thanh ly.
Chi phi thang = khau hao quan tri thang + sua chua that (theo thang nhan lai) + thue / phu cap.
"""
import datetime as _dt

from ecentric_workspace.tai_san import constants as C
from ecentric_workspace.tai_san import depreciation as D

COUNTED_STATUSES = tuple(s for s in C.STATUSES if s != C.ST_DISPOSED)


def _life(a, cats):
    return (cats.get(a.get("asset_category")) or {}).get("ec_default_life_months")


def is_installed(a):
    return bool(a.get(C.INSTALLED_ON_FIELD))


def kpis(assets):
    devices = [a for a in assets if not is_installed(a) and a.get(C.OPS_STATUS_FIELD) != C.ST_DISPOSED]
    by = {s: 0 for s in C.STATUSES}
    for a in devices:
        by[a.get(C.OPS_STATUS_FIELD)] = by.get(a.get(C.OPS_STATUS_FIELD), 0) + 1
    return {"total": len(devices), "by_status": by,
            "components_installed": sum(1 for a in assets if is_installed(a)),
            "in_use": by.get(C.ST_IN_USE, 0), "available": by.get(C.ST_AVAILABLE, 0),
            "reserved": by.get(C.ST_RESERVED, 0), "pending_check": by.get(C.ST_PENDING_CHECK, 0),
            "broken_or_repair": by.get(C.ST_BROKEN, 0) + by.get(C.ST_UNDER_REPAIR, 0),
            "lost": by.get(C.ST_LOST, 0)}


def rent_of(a, ym=None):
    if a.get("ec_ownership") in (C.OWN_RENTED, C.OWN_PERSONAL) and \
            a.get(C.OPS_STATUS_FIELD) not in (C.ST_DISPOSED, C.ST_RETIRED):
        return float(a.get("ec_monthly_rent") or 0)
    return 0.0


def finance(assets, cats, as_of, repair_by_month):
    ym = D.month_key(as_of)
    gross = acc = dep = rent = 0.0
    for a in assets:
        if a.get(C.OPS_STATUS_FIELD) == C.ST_DISPOSED:
            continue
        if a.get("ec_ownership") in (C.OWN_RENTED, C.OWN_PERSONAL):
            rent += rent_of(a)
            continue
        d = D.compute(a, _life(a, cats), ym)
        gross += d["gross"]
        acc += d["accumulated"]
        dep += d["this_month"]
    repair = float(repair_by_month.get(D.month_str(ym), 0))
    return {"gross": gross, "accumulated": acc, "nbv": gross - acc, "month": D.month_str(ym),
            "month_cost": {"depreciation": dep, "repair": repair, "rent": rent,
                           "total": dep + repair + rent}}


def cost_series(assets, cats, as_of, repair_by_month, months=12):
    end = D.month_key(as_of)
    out = []
    for i in range(months - 1, -1, -1):
        ym = D.add_months(end, -i)
        dep = sum(D.month_amount(a, _life(a, cats), ym) for a in assets
                  if a.get("ec_ownership") not in (C.OWN_RENTED, C.OWN_PERSONAL))
        rent = sum(rent_of(a) for a in assets if _started_by(a, ym))
        out.append({"month": D.month_str(ym), "depreciation": dep,
                    "repair": float(repair_by_month.get(D.month_str(ym), 0)), "rent": rent})
    return out


def _started_by(a, ym):
    s = D.start_of(a)
    return bool(s) and D.month_index(s) <= D.month_index(ym)


def by_category(assets):
    out = {}
    for a in assets:
        if is_installed(a) or a.get(C.OPS_STATUS_FIELD) == C.ST_DISPOSED:
            continue
        row = out.setdefault(a.get("asset_category") or "?", {s: 0 for s in C.STATUSES})
        row[a.get(C.OPS_STATUS_FIELD)] = row.get(a.get(C.OPS_STATUS_FIELD), 0) + 1
    return [{"category": k, "counts": v, "total": sum(v.values())}
            for k, v in sorted(out.items(), key=lambda kv: -sum(kv[1].values()))]


def dept_bucket(department, holder):
    """Nhom phong ban hien thi + loc: may co nguoi giu -> phong cua ho (thieu -> Chua gan phong);
    may khong ai giu -> Kho chung (du ban ghi con de phong cu)."""
    if holder:
        return department or C.NO_DEPT_BUCKET
    return C.STOCK_BUCKET


def by_department(assets, cats, as_of, with_cost):
    """May con trong so theo noi dang nam: phong cua nguoi giu; may khong ai giu -> Kho chung; may co
    nguoi giu ma thieu phong -> Chua gan phong (loi du lieu, khong lan voi kho)."""
    out = {}
    for a in assets:
        if is_installed(a) or a.get(C.OPS_STATUS_FIELD) in C.OUT_OF_BOOK:
            continue
        dept = dept_bucket(a.get("department"), a.get("custodian"))
        row = out.setdefault(dept, {"department": dept, "count": 0, "in_use": 0, "nbv": 0.0})
        row["count"] += 1
        row["in_use"] += 1 if a.get(C.OPS_STATUS_FIELD) == C.ST_IN_USE else 0
        if with_cost:
            row["nbv"] += D.compute(a, _life(a, cats), as_of)["nbv"]
    rows = sorted(out.values(), key=lambda r: -r["count"])
    if not with_cost:
        for r in rows:
            r.pop("nbv")
    return rows


def age_buckets(assets, as_of):
    today = D.month_key(as_of)
    counts = [0] * len(C.AGE_BUCKETS)
    for a in assets:
        if is_installed(a) or a.get(C.OPS_STATUS_FIELD) == C.ST_DISPOSED or not a.get("purchase_date"):
            continue
        months = D.month_index(today) - D.month_index(D.month_key(a.get("purchase_date")))
        for i, (limit, _label) in enumerate(C.AGE_BUCKETS):
            if limit is None or months < limit:
                counts[i] += 1
                break
    return [{"bucket": label, "count": counts[i]} for i, (_l, label) in enumerate(C.AGE_BUCKETS)]


def warranty_alerts(assets, today, days=C.WARRANTY_SOON_DAYS):
    out = []
    for a in assets:
        w = a.get("ec_warranty_until")
        if not w or a.get(C.OPS_STATUS_FIELD) in (C.ST_DISPOSED, C.ST_LOST):
            continue
        w = w if isinstance(w, _dt.date) else _dt.date.fromisoformat(str(w)[:10])
        left = (w - today).days
        if 0 <= left <= days:
            out.append({"asset": a["name"], "days_left": left, "warranty_until": str(w)})
    return sorted(out, key=lambda r: r["days_left"])


def fully_depreciated_in_use(assets, cats, as_of):
    return [a["name"] for a in assets
            if a.get(C.OPS_STATUS_FIELD) == C.ST_IN_USE and not is_installed(a)
            and D.compute(a, _life(a, cats), as_of)["fully_depreciated"]]


def idle_assets(assets, last_move, today, days=C.IDLE_ALERT_DAYS):
    """May Sang sang khong dich chuyen qua `days` ngay (lan su kien cuoi, khong co thi ngay mua)."""
    out = []
    for a in assets:
        if a.get(C.OPS_STATUS_FIELD) != C.ST_AVAILABLE or is_installed(a):
            continue
        ref = last_move.get(a["name"]) or a.get("purchase_date")
        if not ref:
            continue
        ref = ref.date() if isinstance(ref, _dt.datetime) else (
            ref if isinstance(ref, _dt.date) else _dt.date.fromisoformat(str(ref)[:10]))
        if (today - ref).days >= days:
            out.append({"asset": a["name"], "idle_days": (today - ref).days})
    return sorted(out, key=lambda r: -r["idle_days"])
