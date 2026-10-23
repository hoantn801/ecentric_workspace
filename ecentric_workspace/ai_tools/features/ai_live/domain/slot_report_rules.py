# Copyright (c) 2026, eCentric and contributors
"""Ke hoach vs thuc te tung khung gio (fix10h, hop dong A8 / 11.3; thuan Python).
App bao lai moi khung: len song luc nao, tre bao lau, gian doan, xuong som / qua gio. ERP ghep voi khung ke hoach
theo (live, planned_start) - so theo THOI DIEM, khong so chuoi. Thoi gian = epoch giay."""
from datetime import datetime

from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.domain import health_rules as R


def _int(v, lo=0, hi=10 ** 7):
    try:
        return max(lo, min(hi, int(float(v))))
    except (TypeError, ValueError):
        return None


def minute(ts):
    """Lam tron toi phut: khoa ghep khung (app gui ISO .000Z, lich ERP theo phut)."""
    return int(round(float(ts) / 60.0)) * 60


def report_key(machine, live, planned_start_ts):
    return "%s|%s|%d" % (machine, live, minute(planned_start_ts))


def sanitize(rec, now):
    """1 SlotRecord cua app -> dict luu; loi -> AiLiveError (bo rieng khung do, khong hong ca lo)."""
    if not isinstance(rec, dict):
        raise C.AiLiveError(C.SlotMsg.BAD % "không phải object")
    live = str(rec.get("live") or "").strip()
    if not C.LIVE_RE.match(live):
        raise C.AiLiveError(C.SlotMsg.BAD % "mã live")
    ps, pe = R.epoch(rec.get("planned_start")), R.epoch(rec.get("planned_end"))
    if not ps or not pe or pe <= ps or pe - ps > 24 * 3600:
        raise C.AiLiveError(C.SlotMsg.BAD % "giờ kế hoạch")
    date = str(rec.get("date") or "")[:10]
    if not C.DATE_RE.match(date):
        date = datetime.fromtimestamp(ps, R._VN).date().isoformat()     # ngay VN cua planned_start
    status = str(rec.get("status") or "").lower()
    start_status = str(rec.get("start_status") or "").lower()
    out = {"live": live, "brand": str(rec.get("brand") or "")[:40], "date": date, "planned_start_ts": float(ps),
           "planned_end_ts": float(pe), "actual_start_ts": float(R.epoch(rec.get("actual_start")) or 0),
           "actual_end_ts": float(R.epoch(rec.get("actual_end")) or 0),
           "start_delay_sec": _int(rec.get("start_delay_sec")), "status": status if status in C.SLOT_STATUSES else "pending",
           "start_status": start_status if start_status in ("on_time", "late") else "",
           "interruptions": _interruptions(rec.get("interruptions")), "downtime_sec": _int(rec.get("downtime_sec")) or 0,
           "ai_failover_count": _int(rec.get("ai_failover_count"), hi=10000) or 0,
           "alerts_critical": _int(rec.get("alerts_critical"), hi=10000) or 0,
           "note": str(rec.get("note") or "")[:C.MAX_ALERT_TEXT], "final": 1 if rec.get("final") else 0,
           "updated_ts": float(R.epoch(rec.get("updated_at")) or now), "session_id": str(rec.get("session_id") or "")[:80]}
    return out


def _interruptions(raw):
    out = []
    for x in (raw if isinstance(raw, list) else [])[:C.MAX_INTERRUPTIONS]:
        if not isinstance(x, dict):
            continue
        a = R.epoch(x.get("from"))
        if not a:
            continue
        reason = str(x.get("reason") or "unknown")
        out.append({"from": float(a), "to": float(R.epoch(x.get("to")) or 0),
                    "reason": reason if reason in C.INTERRUPT_REASONS else "unknown"})
    return out


INTERRUPT_TEXT = {"app_restart": "app mở lại", "resume": "tự phát tiếp", "network": "mất mạng", "esync_down": "mất eSync",
                  "host_missing": "mất host", "tiktok_ended": "sàn tắt live", "unknown": "không rõ"}


def chips(rep, now):
    """Chip ket qua 1 khung (B3): [(tone ok|warn|bad|idle, chu)]."""
    if not rep:
        return []
    st, out = rep.get("status"), []
    if st == "missed":
        return [("bad", "✗ Lỡ")]
    if st == "pending":
        return [("idle", "Chờ giờ")]
    delay = rep.get("start_delay_sec")
    late = rep.get("start_status") == "late" or st == "late" or (delay is not None and delay > C.ON_TIME_S)
    if rep.get("actual_start_ts"):
        out.append(("warn", "⏰ Trễ %d phút" % max(1, int(round((delay or 0) / 60.0)))) if late else ("ok", "✓ Đúng giờ"))
    ints = rep.get("interruptions") or []
    if ints:
        down = int(rep.get("downtime_sec") or 0)
        open_now = [x for x in ints if not x.get("to")]
        down += sum(int(now - x["from"]) for x in open_now if now > x["from"])
        out.append(("warn", "⚡ Gián đoạn %d phút%s" % (max(1, int(round(down / 60.0))), " (%d lần)" % len(ints) if len(ints) > 1 else "")))
    if st == "ended_early":
        out.append(("warn", "Xuống sớm"))
    elif st == "overran":
        out.append(("warn", "Quá giờ"))
    elif st == "stop_failed":
        out.append(("bad", "Không dừng được"))
    if int(rep.get("ai_failover_count") or 0):
        out.append(("warn", "AI dự phòng ×%d" % int(rep["ai_failover_count"])))
    return out or [("idle", "Đang chạy")]


def tone_of(ch):
    rank = {"bad": 3, "warn": 2, "ok": 1, "idle": 0}
    return max((t for t, _ in ch), key=lambda t: rank[t], default="idle")


def match(planned, reports, now, is_erp_live):
    """planned: [{live, title, machine, obs_port, brand, start_ts, end_ts}] (ke hoach ERP 1 ngay);
    reports: [ban ghi da luu]. Tra danh sach dong ke hoach + bao cao khong khop (lich tren may / ke hoach cu)."""
    by_key = {(r["live"], minute(r["planned_start_ts"])): r for r in reports}
    used, rows = set(), []
    for p in planned:
        k = (p["live"], minute(p["start_ts"]))
        rep = by_key.get(k)
        if rep:
            used.add(k)
        no_report = not rep and now > p["start_ts"] + C.NO_REPORT_AFTER_MIN * 60
        ch = chips(rep, now) if rep else ([("idle", "? Không có báo cáo (máy im lặng?)")] if no_report else [])
        rows.append(dict(p, report=_public(rep), chips=[{"tone": t, "text": x} for t, x in ch], tone=tone_of(ch),
                         no_report=no_report, off_plan=False, stale_plan=False))
    for k, rep in by_key.items():
        if k in used:
            continue
        erp = is_erp_live(rep["live"])
        ch = chips(rep, now) + [("idle", "Kế hoạch cũ / lịch trên máy" if erp else "Ngoài kế hoạch ERP")]
        rows.append({"live": rep["live"], "title": rep["live"], "machine": rep.get("machine") or "", "obs_port": 0,
                     "brand": rep.get("brand") or "", "start_ts": rep["planned_start_ts"], "end_ts": rep["planned_end_ts"],
                     "report": _public(rep), "chips": [{"tone": t, "text": x} for t, x in ch], "tone": tone_of(ch),
                     "no_report": False, "off_plan": not erp, "stale_plan": erp})
    rows.sort(key=lambda r: (r["start_ts"], r["machine"], r["live"]))
    return rows


def _public(rep):
    if not rep:
        return None
    return {k: rep.get(k) for k in ("status", "start_status", "actual_start_ts", "actual_end_ts", "start_delay_sec",
                                     "interruptions", "downtime_sec", "ai_failover_count", "alerts_critical", "note",
                                     "final", "updated_ts", "machine")}


def summary(rows):
    """Bo dem cho ngay: dung gio / tre / lo / gian doan / khong bao cao."""
    s = {"planned": 0, "on_time": 0, "late": 0, "missed": 0, "interrupted": 0, "no_report": 0}
    for r in rows:
        if r["off_plan"] or r["stale_plan"]:
            continue
        s["planned"] += 1
        rep = r["report"] or {}
        if r["no_report"]:
            s["no_report"] += 1
        elif rep.get("status") == "missed":
            s["missed"] += 1
        elif rep.get("actual_start_ts"):
            s["late" if any(c["text"].startswith("⏰") for c in r["chips"]) else "on_time"] += 1
        if rep.get("interruptions"):
            s["interrupted"] += 1
    return s
