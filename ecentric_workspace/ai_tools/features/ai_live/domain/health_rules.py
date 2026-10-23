# Copyright (c) 2026, eCentric and contributors
"""Luat giam sat live (thuan Python, khong goi DB): chuan hoa tin hieu may phat, tinh muc canh bao
cua tung live, lich live, chong lap tin bao dong. Thoi gian = epoch giay (UTC)."""
import re
import time
from datetime import datetime, timedelta, timezone

from ecentric_workspace.ai_tools.features.ai_live import constants as C

_VN = timezone(timedelta(hours=C.TZ_OFFSET_H))

#: Ten so lieu chuan -> cac ten app co the gui (W16 thu thap tu OBS GetStats/GetStreamStatus + may).
_METRIC_ALIASES = {
    "fps": ("fps", "stage_fps", "stageFps", "activeFps", "obs_fps"),
    "drop_pct": ("drop_pct", "dropped_pct", "droppedPct", "skipped_pct", "skippedPct"),
    "gpu": ("gpu", "gpu_pct", "gpuPct", "gpu_util"),
    "vram": ("vram", "vram_pct", "vramPct"),
    "cpu": ("cpu", "cpu_pct", "cpuPct", "cpuUsage"),
    "kbps": ("kbps", "bitrate_kbps", "kbpsOut", "bitrate"),
}
_FLAG_ALIASES = {"streaming": ("streaming", "outputActive", "stream_active"),
                 "reconnecting": ("reconnecting", "outputReconnecting")}
_LIMITS = {"fps": 240.0, "drop_pct": 100.0, "gpu": 100.0, "vram": 100.0, "cpu": 100.0, "kbps": 200000.0}


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def _pick(raw, names):
    for n in names:
        if n in raw and raw[n] is not None:
            return raw[n]
    return None


def _epoch(v):
    """ISO / epoch giay / epoch ms -> epoch giay (None neu khong doc duoc)."""
    if v is None or v == "":
        return None
    f = _num(v)
    if f is not None:
        return f / 1000.0 if f > 1e11 else f
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).timestamp()


def epoch(v):
    """Ban cong khai cua _epoch (fix10f: domain/machine_watch_rules dung lai)."""
    return _epoch(v)


def normalize_metrics(raw, now):
    """So lieu gon cho 1 live. Chi giu so trong khoang hop le; chuoi cat ngan."""
    raw = raw if isinstance(raw, dict) else {}
    out = {}
    for k, names in _METRIC_ALIASES.items():
        v = _num(_pick(raw, names))
        if v is not None and 0 <= v <= _LIMITS[k]:
            out[k] = round(v, 2)
    for k, names in _FLAG_ALIASES.items():
        v = _pick(raw, names)
        if isinstance(v, bool) or v in (0, 1):
            out[k] = bool(v)
    age = _num(raw.get("last_comment_age_s"))
    if age is None:
        at = _epoch(_pick(raw, ("last_comment_at", "lastCommentAt")))
        age = max(0.0, now - at) if at else None
    if age is not None and age >= 0:
        out["comment_age_s"] = int(age)
    for k in ("clip", "listener", "obs"):
        if raw.get(k) is not None:
            out[k] = str(raw[k])[:80]
    return out


def metric_reasons(state, m):
    """Canh bao may chu tu tinh tu so lieu (chi khi dang len song)."""
    if state not in C.ON_AIR_STATES:
        return []
    r = []
    if state == "live" and m.get("streaming") is False:
        r.append(("not_streaming", C.Level.CRIT, "OBS không phát lên sàn"))
    if m.get("reconnecting"):
        r.append(("reconnecting", C.Level.WARN, "OBS đang kết nối lại với sàn"))
    if m.get("fps") is not None and m["fps"] < C.FPS_MIN:
        r.append(("low_fps", C.Level.WARN, "Hình chỉ %.0f khung/giây" % m["fps"]))
    if m.get("drop_pct") is not None and m["drop_pct"] > C.DROP_PCT_MAX:
        r.append(("dropped", C.Level.WARN, "Rớt %.1f%% khung hình" % m["drop_pct"]))
    if m.get("gpu") is not None and m["gpu"] > C.GPU_MAX:
        r.append(("gpu_high", C.Level.WARN, "Card đồ hoạ %.0f%%" % m["gpu"]))
    if m.get("vram") is not None and m["vram"] > C.VRAM_MAX:
        r.append(("vram_high", C.Level.WARN, "Bộ nhớ card %.0f%%" % m["vram"]))
    return r


def merge_alerts(app_alerts, server_reasons, prev, now):
    """Gop canh bao app gui + canh bao may chu tinh; giu moc `since` cua ma con ton tai tu lan truoc.
    prev: list cu (da luu). Tra list [{code, level, text, since, src, forward}]."""
    before = {a.get("code"): a for a in (prev or []) if isinstance(a, dict)}
    out, seen = [], set()
    for a in (app_alerts or [])[:C.MAX_HB_ALERTS]:
        if not isinstance(a, dict):
            continue
        code = str(a.get("code") or "").strip().lower()
        level = str(a.get("level") or C.Level.WARN).lower()
        if not C.ALERT_CODE_RE.match(code) or level not in C.APP_ALERT_LEVELS or code in seen:
            continue
        seen.add(code)
        since = _epoch(a.get("since")) or (before.get(code) or {}).get("since") or now
        out.append({"code": code, "level": level, "text": str(a.get("text") or code)[:C.MAX_ALERT_TEXT],
                    "since": min(float(since), now), "src": "app", "forward": bool(a.get("forward"))})
    for code, level, text in server_reasons:
        if code in seen:
            continue
        seen.add(code)
        out.append({"code": code, "level": level, "text": text,
                    "since": (before.get(code) or {}).get("since") or now, "src": "server", "forward": False})
    return out


def _txt(v, n=60):
    return str(v)[:n] if v is not None else ""


def sanitize_extra(lv, prev):
    """fix10h - truong them cua eC Live 1.0.21 cho man Truc live: ai (chinh / du phong), faq (de bam 'Phat FAQ'),
    esync / evoice. Nhip rut gon khong co faq -> giu faq lan truoc."""
    out = dict(prev or {})
    ai = lv.get("ai")
    if isinstance(ai, dict):
        mode = str(ai.get("mode") or "").lower()
        out["ai"] = {"mode": mode if mode in ("main", "backup") else "", "label": _txt(ai.get("label") or ai.get("model")),
                     "provider": _txt(ai.get("provider"), 30)}
    if isinstance(lv.get("faq"), list):
        out["faq"] = [{"id": _txt(f.get("id"), 40), "title": _txt(f.get("title"), 80)}
                      for f in lv["faq"][:C.MAX_FAQ_ITEMS] if isinstance(f, dict) and (f.get("id") or f.get("title"))]
    for k in ("esync", "evoice"):
        v = lv.get(k)
        if isinstance(v, dict):
            out[k] = {kk: (vv if isinstance(vv, (int, float, bool)) or vv is None else _txt(vv, 80))
                      for kk, vv in list(v.items())[:10]}
    return out


def sanitize_schedule(slots):
    """[{days:[1..7] (1 = thu Hai), start:"HH:MM", end:"HH:MM"}]; thieu days = moi ngay."""
    out = []
    for s in (slots or [])[:C.MAX_SLOTS] if isinstance(slots, list) else []:
        if not isinstance(s, dict):
            continue
        a, b = str(s.get("start") or ""), str(s.get("end") or "")
        if not (C.HHMM_RE.match(a) and C.HHMM_RE.match(b)) or a == b:
            continue
        days = [int(d) for d in (s.get("days") or range(1, 8)) if str(d).isdigit() and 1 <= int(d) <= 7]
        row = {"days": sorted(set(days)) or list(range(1, 8)), "start": a, "end": b}
        d = str(s.get("date") or "")[:10]
        if C.DATE_RE.match(d):
            row["date"] = d                      # fix10d: khung chi 1 ngay cu the (lich live ERP)
        out.append(row)
    return out


def _mins(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def in_schedule(slots, now):
    """Bay gio (gio Viet Nam) co nam trong khung live nao khong. Khung qua dem (22:00-02:00) tinh cho ngay bat dau."""
    t = datetime.fromtimestamp(now, _VN)
    cur, wd = t.hour * 60 + t.minute, t.isoweekday()
    prev_wd = 7 if wd == 1 else wd - 1
    today, yday = t.date().isoformat(), (t.date() - timedelta(days=1)).isoformat()
    for s in slots or []:
        a, b = _mins(s["start"]), _mins(s["end"])
        if s.get("date"):                         # khung 1 ngay: chi tinh dung ngay do (+ phan qua dem hom sau)
            if (s["date"] == today and (a <= cur < b if a < b else cur >= a)) or (a > b and s["date"] == yday and cur < b):
                return True
            continue
        if a < b and wd in s["days"] and a <= cur < b:
            return True
        if a > b and ((wd in s["days"] and cur >= a) or (prev_wd in s["days"] and cur < b)):
            return True
    return False


def evaluate(row, now, cfg):
    """Muc cua 1 live tren tuong + ly do. row: ban ghi da luu (state, last_seen_ts, alerts, schedule).
    cfg: {dead_man_min, escalate_min}. Tra {level, reasons:[{code, level, text, since}], stale_s, expected}."""
    age = max(0.0, now - float(row.get("last_seen_ts") or 0))
    expected = row.get("state") in C.ON_AIR_STATES or in_schedule(row.get("schedule") or [], now)
    if age > cfg["dead_man_min"] * 60:
        if not expected:
            return {"level": C.Level.IDLE, "reasons": [], "stale_s": int(age), "expected": False}
        text = C.MonMsg.OFFLINE % int(age // 60)
        return {"level": C.Level.OFF, "stale_s": int(age), "expected": True,
                "reasons": [{"code": "offline", "level": C.Level.CRIT, "text": text, "since": row.get("last_seen_ts")}]}
    reasons = []
    for a in row.get("alerts") or []:
        lv = a["level"]
        if lv == C.Level.WARN and now - float(a.get("since") or now) >= cfg["escalate_min"] * 60:
            lv = C.Level.CRIT
        reasons.append(dict(a, level=lv, escalated=lv != a["level"]))
    if expected and age > C.STALE_WARN_S:
        reasons.append({"code": "stale", "level": C.Level.WARN, "text": "Chậm gửi tín hiệu %d giây" % int(age), "since": now})
    if not expected and not reasons:
        return {"level": C.Level.IDLE, "reasons": [], "stale_s": int(age), "expected": False}
    top = max([C.LEVEL_RANK[r["level"]] for r in reasons] or [0])
    level = {3: C.Level.CRIT, 2: C.Level.WARN}.get(top, C.Level.OK)
    reasons.sort(key=lambda r: -C.LEVEL_RANK[r["level"]])
    return {"level": level, "reasons": reasons, "stale_s": int(age), "expected": expected}


def should_send(last, level, now, dedupe_min):
    """Chong lap: cung khoa chi gui lai sau dedupe_min phut, tru khi muc nang hon lan truoc."""
    if not last:
        return True
    if C.LEVEL_RANK.get(level, 0) > C.LEVEL_RANK.get(last.get("level"), 0):
        return True
    return now - float(last.get("ts") or 0) >= dedupe_min * 60


_TAG = {C.Level.CRIT: "ĐỎ", C.Level.OFF: "ĐỎ", C.Level.WARN: "VÀNG", C.Level.INFO: "XANH", C.Level.OK: "XANH"}


def format_alert(level, row, text):
    """(tieu de, noi dung) cho Teams / Zalo. Khong chua khoa / token."""
    who = " · ".join(x for x in (row.get("brand"), row.get("machine"), row.get("live")) if x)
    title = "[%s] AI Live %s" % (_TAG.get(level, "VÀNG"), who)
    return title, re.sub(r"\s+", " ", str(text or "")).strip()[:500]


def key_of(machine, live):
    """Khoa 1 live tren 1 may (ten DocType EC AI Live Health, ten file anh)."""
    return "%s__%s" % (machine, live)


def now_ts():
    return time.time()


def iso(ts):
    """epoch giay -> ISO 8601 UTC co mili giay (giong Date.toISOString() cua app)."""
    return datetime.fromtimestamp(float(ts), timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (int(float(ts) * 1000) % 1000)
