# Copyright (c) 2026, eCentric and contributors
"""fix10g: tai lich theo ngay cho man Thang (thuan Python): so lan live, so gio, so live cung luc cao nhat tung may,
may vuot so live toi da, vai khung noi bat; tong gio theo brand / may."""
from datetime import datetime

from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.domain import session_rules as S

_VN = S._VN
PRIME_FROM = 17 * 60


def _peak(intervals):
    ev = sorted([(a, 1) for a, b in intervals] + [(b, -1) for a, b in intervals], key=lambda e: (e[0], e[1]))
    cur = top = 0
    for _, d in ev:
        cur += d
        top = max(top, cur)
    return top


def day_load(views, meta, machines, days):
    """views: {id: {slots, machine, enabled}}; meta: {id: {title, brand}}; machines: {code: {max_lives}}.
    Tra (days_out, brand_hours, machine_hours)."""
    out, brand_h, mach_h = [], {}, {}
    for d in days:
        occ = []
        for sid, v in views.items():
            if v.get("enabled"):
                occ += [(a, b, sid, v["machine"]) for a, b, _ in S.occurrences(v["slots"], [d])]
        occ.sort()
        peak, over = {}, []
        for code in {o[3] for o in occ if o[3]}:
            peak[code] = _peak([(a, b) for a, b, _, c in occ if c == code])
            if peak[code] > int((machines.get(code) or {}).get("max_lives") or C.DEFAULT_MAX_LIVES):
                over.append(code)
        hours = 0.0
        for a, b, sid, code in occ:
            h = (b - a) / 3600.0
            hours += h
            brand = meta[sid].get("brand") or ""
            brand_h[brand] = brand_h.get(brand, 0) + h
            if code:
                mach_h[code] = mach_h.get(code, 0) + h
        prime = [o for o in occ if _mins(o[0]) >= PRIME_FROM] or occ
        out.append({"date": d.isoformat(), "n": len(occ), "hours": round(hours, 1), "peak": peak, "over": sorted(over),
                    "chips": [{"start": datetime.fromtimestamp(a, _VN).strftime("%H:%M"), "session": sid,
                               "title": meta[sid]["title"], "brand": meta[sid].get("brand") or "", "machine": code}
                              for a, b, sid, code in prime[:C.MAX_MONTH_CHIPS]]})
    return out, {k: round(v, 1) for k, v in brand_h.items()}, {k: round(v, 1) for k, v in mach_h.items()}


def _mins(ts):
    t = datetime.fromtimestamp(ts, _VN)
    return t.hour * 60 + t.minute
