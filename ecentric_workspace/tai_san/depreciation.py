# Copyright (c) 2026, eCentric and contributors
"""Khau hao QUAN TRI - duong thang, tron thang (khong import frappe, khong ghi so ke toan).

Quy uoc (plan 26/11/2026):
  * Bat dau tu THANG dua vao su dung (ec_depreciation_start, trong = available_for_use_date,
    trong nua = purchase_date). Thang bat dau tinh tron.
  * Moi thang = round((nguyen gia - gia tri thu hoi) / so thang). Thang CUOI lay phan con lai de
    tong khop dung nguyen gia - thu hoi.
  * Dung tu thang SAU ngay ghi giam (ec_end_date: thanh ly / mat).
  * So thang: ec_useful_life_months, trong = Asset Category.ec_default_life_months, trong nua = 36.
"""
import datetime as _dt

from ecentric_workspace.tai_san import constants as C


def month_key(d):
    """date | 'YYYY-MM-DD' | 'YYYY-MM' -> (nam, thang)."""
    if isinstance(d, tuple):
        return d
    if isinstance(d, (_dt.date, _dt.datetime)):
        return (d.year, d.month)
    s = str(d)
    return (int(s[:4]), int(s[5:7]))


def month_index(ym):
    return ym[0] * 12 + ym[1] - 1


def month_from_index(i):
    return (i // 12, i % 12 + 1)


def month_str(ym):
    return "%04d-%02d" % ym


def add_months(ym, n):
    return month_from_index(month_index(ym) + n)


def life_of(asset_life, category_life):
    for v in (asset_life, category_life):
        try:
            if v and int(v) > 0:
                return int(v)
        except (TypeError, ValueError):
            continue
    return C.DEFAULT_LIFE_MONTHS


def start_of(asset):
    for f in ("ec_depreciation_start", "available_for_use_date", "purchase_date"):
        if asset.get(f):
            return month_key(asset.get(f))
    return None


def schedule(gross, salvage, life, start_ym):
    """Danh sach so tien moi thang (do dai = life). Tong = gross - salvage (khong lech dong nao)."""
    base = max(float(gross or 0) - float(salvage or 0), 0.0)
    if life <= 0 or base <= 0:
        return []
    monthly = round(base / life)
    rows = [float(monthly)] * (life - 1)
    rows.append(base - monthly * (life - 1))
    return rows


def compute(asset, category_life=None, as_of=None):
    """Trang thai khau hao cua mot tai san tai thang `as_of` (mac dinh: thang hien tai).

    asset: dict co net_purchase_amount, ec_salvage_value, ec_useful_life_months,
    ec_depreciation_start / available_for_use_date / purchase_date, ec_end_date.
    """
    gross = float(asset.get("net_purchase_amount") or 0)
    salvage = float(asset.get("ec_salvage_value") or 0)
    life = life_of(asset.get("ec_useful_life_months"), category_life)
    start = start_of(asset)
    out = {"gross": gross, "salvage": salvage, "life": life, "start": None, "end": None,
           "monthly": 0.0, "months_done": 0, "accumulated": 0.0, "nbv": gross,
           "this_month": 0.0, "fully_depreciated": False}
    if not start or gross <= 0:
        return out
    rows = schedule(gross, salvage, life, start)
    now = month_key(as_of or _dt.date.today())
    stop = month_index(now)
    if asset.get("ec_end_date"):
        stop = min(stop, month_index(month_key(asset.get("ec_end_date"))))
    done = max(0, min(life, stop - month_index(start) + 1))
    acc = sum(rows[:done])
    in_window = month_index(start) <= month_index(now) <= month_index(start) + life - 1
    ended = asset.get("ec_end_date") and month_index(now) > month_index(month_key(asset.get("ec_end_date")))
    this = rows[month_index(now) - month_index(start)] if (rows and in_window and not ended) else 0.0
    out.update({"start": month_str(start), "end": month_str(add_months(start, life - 1)),
                "monthly": rows[0] if rows else 0.0, "months_done": done, "accumulated": acc,
                "nbv": gross - acc, "this_month": this, "fully_depreciated": done >= life})
    return out


def month_amount(asset, category_life, ym):
    """Khau hao cua RIENG thang ym (0 ngoai cua so hoac sau ngay ghi giam)."""
    return compute(asset, category_life, ym)["this_month"]


def nbv_curve(asset, category_life=None, points=None):
    """[(thang, gia tri con lai)] tu thang bat dau den het khau hao - cho bieu do nho."""
    d = compute(asset, category_life)
    if not d["start"]:
        return []
    rows = schedule(d["gross"], d["salvage"], d["life"], month_key(d["start"]))
    start = month_key(d["start"])
    out, left = [], d["gross"]
    for i, amt in enumerate(rows):
        left -= amt
        out.append((month_str(add_months(start, i)), left))
    if points and len(out) > points:
        step = max(1, len(out) // points)
        out = out[::step] + ([out[-1]] if out[-1] not in out[::step] else [])
    return out
