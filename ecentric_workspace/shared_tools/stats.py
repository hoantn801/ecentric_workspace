# Copyright (c) 2026, eCentric and contributors
"""Thong ke dung chung cho quan ly - HAM THUAN (khong frappe): nhan cac luot + file xuat trong ky,
tra ve so lieu cho trang /kalodata (khoi "Thong ke", chi quan ly thay).

Luot (dict): user, status, end_reason, joined_at, ready_at, started_at, ended_at.
File (dict): user, rows, pages, run_id, part, exported_at.
"""
import datetime as dt

from ecentric_workspace.shared_tools import constants as C

TOP_USERS = 10
DAILY_DAYS = 14


def _minutes(a, b):
    return max((b - a).total_seconds() / 60.0, 0.0) if a and b else 0.0


def compute(entries, exports, meta, now, days):
    since = now - dt.timedelta(days=days)
    used = [e for e in entries if e.get("started_at") and e["started_at"] >= since]
    readied = [e for e in entries if e.get("ready_at") and e["ready_at"] >= since]
    no_show = [e for e in readied if e.get("end_reason") == C.END_NO_SHOW]
    idle = [e for e in used if e.get("end_reason") == C.END_IDLE]
    waits = [_minutes(e["joined_at"], e["ready_at"]) for e in readied if e.get("joined_at")]

    def end_of(e):
        return e.get("ended_at") or (now if e.get("status") == C.ST_ACTIVE else e.get("ends_at")) or e["started_at"]

    per_user, hours = {}, [0] * 24
    days_map = {(now.date() - dt.timedelta(days=i)): 0.0 for i in range(DAILY_DAYS)}
    total_min = 0.0
    for e in used:
        m = _minutes(e["started_at"], end_of(e))
        total_min += m
        u = per_user.setdefault(e["user"], {"sessions": 0, "minutes": 0.0, "rows": 0, "exports": 0})
        u["sessions"] += 1
        u["minutes"] += m
        hours[e["started_at"].hour] += 1
        d = e["started_at"].date()
        if d in days_map:
            days_map[d] += m
    ex = [x for x in exports if x.get("exported_at") and x["exported_at"] >= since]
    runs = set()
    for x in ex:
        u = per_user.setdefault(x["user"], {"sessions": 0, "minutes": 0.0, "rows": 0, "exports": 0})
        u["rows"] += int(x.get("rows") or 0)
        key = x.get("run_id") if int(x.get("part") or 0) > 0 and x.get("run_id") else x.get("name")
        if (x["user"], key) not in runs:
            runs.add((x["user"], key))
            u["exports"] += 1
    top = sorted(per_user.items(), key=lambda kv: (-kv[1]["minutes"], -kv[1]["rows"]))[:TOP_USERS]
    return {
        "days": days,
        "kpi": {
            "sessions": len(used),
            "users": len({e["user"] for e in used}),
            "hours": round(total_min / 60.0, 1),
            "exports": len(runs),
            "rows": sum(int(x.get("rows") or 0) for x in ex),
            "pages": sum(int(x.get("pages") or 0) for x in ex),
            "avg_wait_min": round(sum(waits) / len(waits), 1) if waits else 0,
            "no_show_pct": round(100.0 * len(no_show) / len(readied)) if readied else 0,
            "idle_end": len(idle),
        },
        "by_hour": hours,
        "by_day": [{"date": d.strftime("%d/%m"), "minutes": round(days_map[d])} for d in sorted(days_map)],
        "top": [{"name": (meta.get(u) or {}).get("full_name") or u, "department": (meta.get(u) or {}).get("department") or "",
                 "sessions": v["sessions"], "minutes": round(v["minutes"]), "exports": v["exports"], "rows": v["rows"]}
                for u, v in top],
    }
