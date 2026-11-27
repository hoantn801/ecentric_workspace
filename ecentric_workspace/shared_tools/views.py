# Copyright (c) 2026, eCentric and contributors
"""Doc cho trang /kalodata: mot lan goi tra du du lieu ve ca 3 trang thai (cho / den luot / dang dung).

Thoi gian gui dang SO GIAY CON LAI tinh o server (trang dem nguoc tu do) -> dong ho may nguoi dung
lech cung khong sai. Khong tra email nguoi khac: chi ho ten + phong ban.
"""
from frappe.utils import add_days, now_datetime

from ecentric_workspace.shared_tools import constants as C
from ecentric_workspace.shared_tools import queue_rules as Q
from ecentric_workspace.shared_tools import repository as R
from ecentric_workspace.shared_tools import service as S


def _secs(delta):
    return max(int(delta.total_seconds()), 0)


def _initials(name):
    parts = [p for p in (name or "").split() if p]
    if not parts:
        return "?"
    return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper()


def _hhmm(d):
    return d.strftime("%H:%M") if d else ""


def host_view(host):
    if host.get("ok"):
        return {"ok": True, "label": "Máy online"}
    if host.get("reason") == "not_configured":
        return {"ok": False, "label": "Chưa nối máy"}
    return {"ok": False, "label": "Máy offline"}


def state(ctx, key):
    tool = S.load_tool(ctx, key)
    host = S.host_state(key)
    S.tick(key, host=host)
    # May bao co file cho -> keo luon (khong doi job moi phut: scheduler co the tre / dung khi site deploy,
    # do 27/11 file 3000 dong nam cho 3+ phut). Khoa ngan de nhieu trang dang mo khong keo trung.
    if host.get("ok") and int(host.get("exports_pending") or 0) and R.try_lock(C.CACHE_EXPORT_LOCK % key, 30):
        from ecentric_workspace.shared_tools import exports as X
        X.sync(key, host=host)
    now = now_datetime()
    cfg = Q.cfg_of(tool)
    entries = Q.ordered(R.open_entries(key))
    meta = R.user_meta([e["user"] for e in entries])
    me = Q.mine(entries, ctx.user)
    return {
        "tool": {"key": key, "title": tool.title, "notice": tool.notice or "", "enabled": bool(tool.enabled),
                 "lease": cfg["lease"],
                 "ready": cfg["ready"], "extend": cfg["extend"], "idle": cfg["idle"]},
        "host": host_view(host),
        "me": _me(entries, me, now, cfg),
        "queue": [_row(e, i, entries, ctx, meta, now, cfg) for i, e in enumerate(entries)],
        "holder": _holder(entries, meta, now),
        "exports": _exports(key, ctx.user, now),
        "is_manager": ctx.is_manager,
        "poll_sec": C.POLL_SEC,
    }


def _me(entries, me, now, cfg):
    if not me:
        return {"status": None}
    out = {"status": me["status"], "entry": me["name"], "waiting_after": Q.waiting_after(entries, me)}
    if me["status"] == C.ST_WAITING:
        waiters = [e for e in entries if e["status"] == C.ST_WAITING]
        out["position"] = next(i for i, e in enumerate(waiters) if e["name"] == me["name"]) + 1
        out["eta_min"] = Q.eta_minutes(entries, me, now, cfg)
    elif me["status"] == C.ST_READY:
        deadline = me["ready_at"] + Q.minutes(cfg["ready"])
        out["ready_left_sec"] = _secs(deadline - now)
    elif me["status"] == C.ST_ACTIVE:
        out["remaining_sec"] = _secs(me["ends_at"] - now)
        out["total_sec"] = _secs(me["ends_at"] - me["started_at"]) or cfg["lease"] * 60
        out["started"] = _hhmm(me["started_at"])
        out["ends"] = _hhmm(me["ends_at"])
        out["extend_reason"] = Q.extend_check(entries, me, now)
    return out


def _row(e, i, entries, ctx, meta, now, cfg):
    m = meta.get(e["user"]) or {}
    name = m.get("full_name") or e.get("full_name") or "?"
    row = {"entry": e["name"], "status": e["status"], "status_label": C.STATUS_LABELS[e["status"]],
           "name": name, "initials": _initials(name), "department": m.get("department") or "",
           "is_me": e["user"] == ctx.user}
    if e["status"] == C.ST_ACTIVE:
        row["meta"] = "còn %d phút" % (_secs(e["ends_at"] - now) // 60)
    elif e["status"] == C.ST_READY:
        row["meta"] = "đang mở"
    else:
        row["pos"] = len([x for x in entries[:i + 1] if x["status"] == C.ST_WAITING])
        row["meta"] = "chờ ~%d phút" % Q.eta_minutes(entries, e, now, cfg)
    return row


def _holder(entries, meta, now):
    h = Q.holder(entries)
    if not h:
        return None
    m = meta.get(h["user"]) or {}
    out = {"name": m.get("full_name") or h.get("full_name"), "department": m.get("department") or "",
           "status": h["status"]}
    if h["status"] == C.ST_ACTIVE:
        out["since"] = _hhmm(h["started_at"])
        out["remaining_min"] = _secs(h["ends_at"] - now) // 60
    return out


STATS_DAYS = (7, 30, 90)


def stats(ctx, key, days=30):
    """Thong ke cho quan ly (System Manager / EC Shared Tool Manager)."""
    from ecentric_workspace.shared_tools import stats as ST
    S.load_tool(ctx, key)
    if not ctx.is_manager:
        raise Q.QueueError("Chỉ quản lý công cụ xem được thống kê.")
    days = days if days in STATS_DAYS else 30
    now = now_datetime()
    # Lay rong hon 1 ngay: luot vao hang truoc ky nhung bat dau dung trong ky van tinh.
    entries = R.entries_since(key, add_days(now, -days - 1))
    exports = R.exports_since(key, add_days(now, -days))
    meta = R.user_meta([e["user"] for e in entries] + [x["user"] for x in exports])
    return ST.compute(entries, exports, meta, now, days)


MAX_FILE_ITEMS = 120  # trang chia 5 dong / trang (ec_st_kalodata.js FILES_PER_PAGE)


def _exports(key, user, now):
    return group_exports(R.exports_of(key, user, add_days(now, -C.EXPORT_KEEP_DAYS)), now)


def group_exports(rows, now):
    """Cac phan cung run_id gop thanh MOT dong (tai gop Excel + tung phan); file le giu nguyen.
    rows: moi nhat truoc. Ham thuan (test duoc)."""
    out, runs = [], {}
    for r in rows:
        src = C.EXPORT_SOURCE_LABELS.get(r.get("source"), r.get("source"))
        if r.get("run_id") and int(r.get("part") or 0) > 0:
            g = runs.get(r["run_id"])
            if g is None:
                g = runs[r["run_id"]] = {"kind": "run", "run": r["run_id"], "source": src, "rows": 0, "pages": 0,
                                         "page": (r.get("page_title") or "").split(" (phần")[0], "parts": [],
                                         "at": _when(r.get("exported_at"), now), "new": False,
                                         **_day(r.get("exported_at"), now)}
                out.append(g)
            g["rows"] += int(r.get("rows") or 0)
            g["pages"] += int(r.get("pages") or 0)
            g["new"] = g["new"] or not r.get("downloaded_at")
            g["parts"].append({"name": r["name"], "part": int(r.get("part") or 0), "rows": r.get("rows")})
            continue
        out.append({"kind": "file", "name": r["name"], "file_name": r.get("file_name"), "rows": r.get("rows"),
                    "pages": r.get("pages"), "page": r.get("page_title") or "", "source": src,
                    "at": _when(r.get("exported_at"), now), "new": not r.get("downloaded_at"),
                    **_day(r.get("exported_at"), now)})
    for g in runs.values():
        g["parts"].sort(key=lambda x: x["part"])
    return out[:MAX_FILE_ITEMS]


def _day(d, now):
    """Nhom theo ngay cho danh sach file: {"day": "Hôm nay" | "Hôm qua" | "dd/mm", "time": "HH:MM"}."""
    if not d:
        return {"day": "", "time": ""}
    gap = (now.date() - d.date()).days
    return {"day": "Hôm nay" if gap == 0 else "Hôm qua" if gap == 1 else d.strftime("%d/%m"), "time": _hhmm(d)}


def _when(d, now):
    if not d:
        return ""
    if d.date() == now.date():
        return _hhmm(d)
    if (now.date() - d.date()).days == 1:
        return "Hôm qua " + _hhmm(d)
    return d.strftime("%d/%m %H:%M")
