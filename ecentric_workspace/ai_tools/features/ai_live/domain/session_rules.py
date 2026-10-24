# Copyright (c) 2026, eCentric and contributors
"""Luat Phien live + Lich live (thuan Python, khong goi DB): chuan hoa phien / khung gio, trung gio trong 1 phien,
suc chua may phat (toi da N live cung luc), khung ke tiep, trang thai tren danh sach, chuan hoa khoi "detail".
Gio = gio Viet Nam (UTC+7); khung qua dem (22:00-02:00) tinh cho ngay bat dau."""
from datetime import date, datetime, timedelta

from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.domain import health_rules as R

_VN = R._VN


def _mins(hhmm):
    h, m = str(hhmm).split(":")
    return int(h) * 60 + int(m)


def _parse_days(v):
    """[1..7] | "1,2,3" | "1-5" | "" (= moi ngay) -> list da sap xep."""
    if isinstance(v, (list, tuple)):
        items = [str(x) for x in v]
    else:
        items = [x.strip() for x in str(v or "").replace(";", ",").split(",") if x.strip()]
    out = set()
    for it in items:
        if "-" in it:
            a, _, b = it.partition("-")
            if not (a.strip().isdigit() and b.strip().isdigit()):
                raise C.AiLiveError("thứ không hợp lệ: %s" % it)
            out.update(range(int(a), int(b) + 1))
        elif it.isdigit():
            out.add(int(it))
        else:
            raise C.AiLiveError("thứ không hợp lệ: %s" % it)
    if any(d < 1 or d > 7 for d in out):
        raise C.AiLiveError("thứ phải từ 1 (thứ Hai) đến 7 (Chủ nhật)")
    return sorted(out) or list(range(1, 8))


def norm_slots(slots):
    """[{days, date, start, end}] -> list chuan; loi -> AiLiveError co so thu tu khung (1-based)."""
    out = []
    for i, s in enumerate(slots or [], 1):
        s = s if isinstance(s, dict) else {}
        try:
            a, b = str(s.get("start") or "").strip(), str(s.get("end") or "").strip()
            if not (C.HHMM_RE.match(a) and C.HHMM_RE.match(b)):
                raise C.AiLiveError("giờ phải dạng HH:MM (vd 19:00)")
            if a == b:
                raise C.AiLiveError("giờ bắt đầu và kết thúc trùng nhau")
            d = str(s.get("date") or "").strip()[:10]
            if d and not C.DATE_RE.match(d):
                raise C.AiLiveError("ngày phải dạng YYYY-MM-DD")
            if (_mins(b) - _mins(a)) % 1440 < C.MIN_SLOT_MIN:
                raise C.AiLiveError(C.ContractMsg.SLOT_TOO_SHORT % C.MIN_SLOT_MIN)
            out.append({"days": [] if d else _parse_days(s.get("days")), "date": d or None, "start": a, "end": b})
        except C.AiLiveError as e:
            raise C.AiLiveError(C.SessMsg.BAD_SLOT % (i, e))
    if len(out) > C.MAX_SESSION_SLOTS:
        raise C.AiLiveError(C.SessMsg.BAD_SLOT % (len(out), "tối đa %d khung" % C.MAX_SESSION_SLOTS))
    # fix10g: thu tu on dinh (app dat ma khung erp1, erp2... theo thu tu): lap hang tuan truoc, roi ngay cu the; theo gio
    return sorted(out, key=lambda s: (s["date"] or "", s["days"], s["start"]))


def _applies(slot, day):
    return slot["date"] == day.isoformat() if slot["date"] else day.isoweekday() in slot["days"]


def occurrences(slots, days):
    """Cac lan dien ra trong cac ngay `days` (date): [(start_ts, end_ts, slot_index)] - epoch giay."""
    out = []
    for i, s in enumerate(slots):
        a, b = _mins(s["start"]), _mins(s["end"])
        for day in days:
            if not _applies(s, day):
                continue
            base = datetime(day.year, day.month, day.day, tzinfo=_VN).timestamp()
            out.append((base + a * 60, base + (b if b > a else b + 1440) * 60, i))
    return sorted(out)


def horizon(slot_lists, today):
    """Tap ngay can xet trung gio: tuan hien tai + 1 ngay (khung qua dem), cong cac ngay cu the (+-1)."""
    days = {today + timedelta(days=k) for k in range(-1, 8)}
    for slots in slot_lists:
        for s in slots:
            if s["date"]:
                d = date.fromisoformat(s["date"])
                days.update({d - timedelta(days=1), d, d + timedelta(days=1)})
    return sorted(days)


def self_overlap(slots, today):
    """Khung nao cua chinh phien trung nhau -> (i, j) 1-based hoac None."""
    occ = occurrences(slots, horizon([slots], today))
    for k in range(1, len(occ)):
        for p in range(k):
            if occ[p][2] != occ[k][2] and occ[k][0] < occ[p][1] and occ[p][0] < occ[k][1]:
                return sorted((occ[p][2] + 1, occ[k][2] + 1))
    return None


def capacity_conflicts(sessions, max_lives, today):
    """sessions: [{id, slots}] cung 1 may (dang bat). Tra [{start, end, ids}] cac doan > max_lives live cung luc."""
    lists = [s["slots"] for s in sessions]
    days = horizon(lists, today)
    ev = []
    for s in sessions:
        for a, b, _ in occurrences(s["slots"], days):
            ev.append((a, 1, s["id"]))
            ev.append((b, -1, s["id"]))
    ev.sort(key=lambda e: (e[0], e[1]))
    live, out = {}, []
    for t, d, sid in ev:
        live[sid] = live.get(sid, 0) + d
        on = [k for k, v in live.items() if v > 0]
        if d > 0 and len(on) > max_lives:
            out.append({"start": t, "ids": sorted(on)})
    return out


def window_now(slots, now):
    """(start_ts, end_ts) cua khung dang dien ra, hoac None."""
    today = datetime.fromtimestamp(now, _VN).date()
    for a, b, _ in occurrences(slots, [today - timedelta(days=1), today]):
        if a <= now < b:
            return a, b
    return None


def next_window(slots, now, days_ahead=8):
    """Khung dang dien ra hoac sap toi gan nhat trong `days_ahead` ngay: (start_ts, end_ts) hoac None."""
    today = datetime.fromtimestamp(now, _VN).date()
    for a, b, _ in occurrences(slots, [today + timedelta(days=k) for k in range(-1, days_ahead)]):
        if b > now:
            return a, b
    return None


def status_of(session, health_row, ev, now, dead_man_min):
    """Trang thai 1 phien tren danh sach: on_air / problem / scheduled / off."""
    if not session.get("enabled"):
        return C.SessionStatus.OFF
    in_win = window_now(session.get("slots") or [], now) is not None
    fresh = bool(health_row) and now - float(health_row.get("last_seen_ts") or 0) <= dead_man_min * 60
    if ev and ev.get("level") in (C.Level.CRIT, C.Level.OFF, C.Level.WARN):
        return C.SessionStatus.PROBLEM
    if in_win and not fresh:
        return C.SessionStatus.PROBLEM
    if fresh and health_row.get("state") in C.ON_AIR_STATES:
        return C.SessionStatus.ON_AIR
    if next_window(session.get("slots") or [], now):
        return C.SessionStatus.SCHEDULED
    return C.SessionStatus.OFF


def to_app_schedule(slots):
    """Khung cho app / tin hieu: {days, start, end} (+ date neu chi 1 ngay)."""
    return [{"days": s["days"] or list(range(1, 8)), "start": s["start"], "end": s["end"], **({"date": s["date"]} if s["date"] else {})}
            for s in slots]


def _txt(v, n=C.MAX_DETAIL_TEXT):
    return str(v if v is not None else "")[:n]


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def sanitize_detail(raw, now):
    """Khoi chi tiet app gui kem tin hieu: cat ngan, chi giu truong biet truoc. Khong hop le -> None."""
    if not isinstance(raw, dict):
        return None
    pick = lambda d, keys: {k: (_txt(d.get(k)) if not isinstance(d.get(k), (int, float)) else d.get(k)) for k in keys if d.get(k) is not None}  # noqa: E731
    nw = raw.get("now") if isinstance(raw.get("now"), dict) else {}
    out = {"at": now, "now": {**pick(nw, ("kind", "file", "product")),
                              **{k: R._epoch(nw.get(k)) for k in ("started_at", "ends_at") if R._epoch(nw.get(k))}}}
    shapes = {"next": ("kind", "product", "file", "eta_s"), "queue": ("user", "question", "state"),
              "recent": ("at", "user", "text", "handled"), "greeted": ("at", "name", "mode")}
    for key, keys in shapes.items():
        items = raw.get(key) if isinstance(raw.get(key), list) else []
        out[key] = [pick(x, keys) for x in items[:C.DETAIL_LIMITS[key]] if isinstance(x, dict)]
    cnt = raw.get("counters") if isinstance(raw.get("counters"), dict) else {}
    out["counters"] = {k: int(_num(cnt.get(k)) or 0) for k in C.DETAIL_COUNTERS if _num(cnt.get(k)) is not None}
    cost = _num(raw.get("cost_today_usd"))
    out["cost_today_usd"] = round(cost, 4) if cost is not None and 0 <= cost <= C.MAX_USD else None
    pf = raw.get("platform") if isinstance(raw.get("platform"), dict) else {}
    out["platform"] = {k: (int(_num(pf[k])) if k != "status" and _num(pf.get(k)) is not None else _txt(pf.get(k), 40))
                       for k in ("status", "viewers", "likes", "orders") if pf.get(k) is not None}
    return out


def sanitize_summary(raw, now):
    """Tong ket cuoi phien app gui: {session, started_at, ended_at, duration_s, counters, cost_usd, alerts, reason}.
    Thieu ma phien / gio bat dau -> AiLiveError."""
    if not isinstance(raw, dict):
        raise C.AiLiveError(C.MonMsg.BAD_HB % "tổng kết phiên")
    sid = str(raw.get("session") or raw.get("session_id") or "").strip()
    if not C.SESSION_RE.match(sid):
        raise C.AiLiveError(C.MonMsg.BAD_HB % "mã phiên trong tổng kết")
    dur = _num(raw.get("duration_s"))
    start = R._epoch(raw.get("started_at"))
    # 1.0.21: crash_resume gui ended_at = null (phien bi ngat) -> lay bat dau + thoi luong neu co, khong thi gio nhan
    end = R._epoch(raw.get("ended_at")) or (start + dur if start and dur is not None and dur >= 0 else now)
    if not start or start > now + 300 or end < start:
        raise C.AiLiveError(C.MonMsg.BAD_HB % "giờ bắt đầu / kết thúc")
    cnt = raw.get("counters") if isinstance(raw.get("counters"), dict) else raw
    cost = _num(raw.get("cost_usd"))
    reason = str(raw.get("reason") or "other")
    return {"session": sid, "started_ts": start, "ended_ts": min(end, now + 300),
            "duration_s": int(dur) if dur is not None and 0 <= dur <= 7 * 86400 else int(end - start),
            "counters": {k: max(0, int(_num(cnt.get(k)) or 0)) for k in C.DETAIL_COUNTERS},
            "cost_usd": round(cost, 4) if cost is not None and 0 <= cost <= C.MAX_USD else 0.0,
            "alerts": max(0, int(_num(raw.get("alerts")) or 0)),
            "reason": reason if reason in C.SUMMARY_REASONS else "other"}
