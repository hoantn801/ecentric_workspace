# Copyright (c) 2026, eCentric and contributors
"""Luat "may im lang" (W17, thuan Python, khong goi DB): rut gon nhip tim ca may, xet may mat lien lac
khi dang co live, nhac lai theo gio, bao lien lac lai (khoi dong lai / mo lai app). Thoi gian = epoch giay."""
from datetime import datetime, timedelta, timezone

from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.domain import health_rules as R
from ecentric_workspace.ai_tools.features.ai_live.domain import session_rules as S

_VN = timezone(timedelta(hours=C.TZ_OFFSET_H))
_LV = {C.Level.CRIT: "đỏ", C.Level.WARN: "vàng", C.Level.INFO: "xanh"}


def _live_list(lives):
    return [lv for lv in (lives or []) if isinstance(lv, dict) and C.LIVE_RE.match(str(lv.get("live") or ""))]


def on_air_lives(payload, lives):
    """Live dang len song o nhip nay: state preflight/live/ending, hoac on_air (1.0.20) = true / danh sach ma live."""
    lives, flag = _live_list(lives), payload.get("on_air")
    # 1.0.21: on_air = [{live, brand, mode, talking, since}]; ban cu: true / danh sach ma live
    objs = [x for x in flag if isinstance(x, dict) and C.LIVE_RE.match(str(x.get("live") or ""))] if isinstance(flag, list) else []
    named = {str(x) for x in flag if not isinstance(x, dict)} if isinstance(flag, list) else set()
    out = [{"live": str(x["live"]), "brand": str(x.get("brand") or "")[:40]} for x in objs]
    seen = {x["live"] for x in out}
    for lv in lives:
        if lv["live"] not in seen and (str(lv.get("state") or "").lower() in C.ON_AIR_STATES or str(lv["live"]) in named
                                       or (flag is True and not objs)):
            out.append({"live": str(lv["live"]), "brand": str(lv.get("brand") or "")[:40]})
            seen.add(lv["live"])
    return out[:C.MAX_HB_LIVES]


def active_alerts(lives, problems=None):
    """Bao dong dang con: problems[] cap may (1.0.21, da gom ca bao dong tung live) neu co, khong thi alerts tung live.
    Dong "<live>: <noi dung> (do|vang)"; do truoc."""
    if isinstance(problems, list):
        rows = [p for p in problems[:C.MAX_HB_PROBLEMS] if isinstance(p, dict)]
        rows = [p for p in rows if str(p.get("level") or "").lower() in (C.Level.WARN, C.Level.CRIT)]
        rows.sort(key=lambda p: str(p.get("level")).lower() != C.Level.CRIT)
        return [("%s: " % p["live"] if p.get("live") else "") + "%s (%s)" % (str(p.get("text") or p.get("rule") or "")[:80],
                _LV[str(p["level"]).lower()]) for p in rows][:C.MAX_MACHINE_ALERTS]
    out = []
    for lv in _live_list(lives):
        for a in (lv.get("alerts") or [])[:C.MAX_HB_ALERTS]:
            level = str((a or {}).get("level") or C.Level.WARN).lower() if isinstance(a, dict) else ""
            if level in (C.Level.WARN, C.Level.CRIT):
                text = str(a.get("text") or a.get("code") or "")[:80]
                out.append("%s: %s (%s)" % (lv["live"], text, _LV[level]))
    return out[:C.MAX_MACHINE_ALERTS]


def heartbeat_vals(payload, lives, machine, now):
    """Gia tri luu len EC AI Live Machine moi nhip tim. Dang mat lien lac ma co nhip lai -> ghi watch_back_ts."""
    app = payload.get("app") if isinstance(payload.get("app"), dict) else {}
    state = str(payload.get("state") or "").lower()
    resume = payload.get("resume") if isinstance(payload.get("resume"), dict) else {}
    lives_now = on_air_lives(payload, lives)
    vals = {"hb_last_seen_ts": now, "hb_state": state if state in C.APP_STATES else C.APP_RUNNING,
            "hb_version": str(app.get("version") or "")[:20], "hb_boot_ts": R.epoch(payload.get("boot_at")) or 0,
            "hb_started_ts": R.epoch(payload.get("app_started_at")) or 0, "hb_on_air": 1 if lives_now else 0,
            "hb_lives": lives_now, "hb_alerts": active_alerts(lives, payload.get("problems")),
            "hb_resume_crash": 1 if resume.get("from_crash") else 0, "hb_resume": _resume_text(resume)}
    at = R.epoch(payload.get("at"))
    if at:                                       # fix10g: dong ho may lech so voi ERP (lich chay theo gio may)
        vals["hb_clock_skew_s"] = round(at - now, 1)
    if float(machine.get("watch_lost_ts") or 0) > 0 and not float(machine.get("watch_back_ts") or 0):
        vals["watch_back_ts"] = now
    return vals


def _resume_text(resume):
    """1.0.21 resume = {resumed_at, from_crash, lives, ok, failed} -> 'tu phat tiep: OK L1 · loi L2' (rong neu khong co)."""
    ok = [str(x) for x in resume.get("ok") or [] if not isinstance(x, (dict, list))][:10]
    bad = [str(x) for x in resume.get("failed") or [] if not isinstance(x, (dict, list))][:10]
    if not (ok or bad):
        return ""
    return C.WatchMsg.RESUME % (", ".join(ok) or "–", ", ".join(bad) or "–")


def silent_s(m, now):
    """So giay may chua gui nhip tim; None neu may chua tung gui (chua theo doi)."""
    last = float(m.get("hb_last_seen_ts") or 0)
    return max(0.0, now - last) if last > 0 else None


def covers_live_offline(m, now, dead_man_min):
    """Ca may im lang (hoac tat app dung cach) -> bao theo MAY, khong bao tung live."""
    age = silent_s(m or {}, now)
    return age is not None and (age > dead_man_min * 60 or (m or {}).get("hb_state") == C.APP_STOPPING)


def _in_minutes(hhmm, default):
    h, m = (hhmm if C.HHMM_RE.match(str(hhmm or "")) else default).split(":")
    return int(h) * 60 + int(m)


def repeat_minutes(now, cfg):
    """5 phut/lan; trong khung dem (mac dinh 01:00-07:00, gio VN) 15 phut/lan."""
    t = datetime.fromtimestamp(now, _VN)
    cur = t.hour * 60 + t.minute
    a = _in_minutes(cfg.get("night_start"), C.NIGHT_START)
    b = _in_minutes(cfg.get("night_end"), C.NIGHT_END)
    night = (a <= cur < b) if a < b else (a != b and (cur >= a or cur < b))
    if night:
        return int(cfg.get("night_repeat_min") or C.NIGHT_REPEAT_MIN)
    return int(cfg.get("machine_repeat_min") or C.MACHINE_REPEAT_MIN)


def expected_lives(m, sessions, health_rows, now):
    """Live cua may luc nay: dang len song o nhip cuoi + phien ERP dang trong khung gio + lich app gui kem.
    Tra [{live, brand, name}] khong trung ma live."""
    code, out = m["machine_code"], {}
    for lv in m.get("hb_lives") or []:
        out.setdefault(lv["live"], {"live": lv["live"], "brand": lv.get("brand") or "", "name": lv["live"]})
    for s in sessions or []:
        if s.get("machine") == code and s.get("enabled") and S.window_now(s.get("slots") or [], now):
            out[s["id"]] = {"live": s["id"], "brand": s.get("brand") or "", "name": s.get("title") or s["id"]}
    for h in health_rows or []:
        if h.get("machine") == code and R.in_schedule(h.get("schedule") or [], now):
            out.setdefault(h["live"], {"live": h["live"], "brand": h.get("brand") or "", "name": h["live"]})
    return list(out.values())


def machine_name(m):
    return "%s (%s)" % (m["machine_code"], m["label"]) if m.get("label") else m["machine_code"]


def _clock(ts, now):
    t, today = datetime.fromtimestamp(ts, _VN), datetime.fromtimestamp(now, _VN).date()
    return t.strftime("%H:%M") + ("" if t.date() == today else C.WatchMsg.DAY % t.strftime("%d/%m"))


def _lives_text(lives):
    return ", ".join("%s – %s" % (x["brand"], x["name"]) if x.get("brand") else x["name"] for x in lives)


def _back_reason(m):
    boot, lost_boot = float(m.get("hb_boot_ts") or 0), float(m.get("watch_lost_boot_ts") or 0)
    if boot and lost_boot and boot - lost_boot > C.REBOOT_TOLERANCE_S:
        return C.WatchMsg.REBOOT
    started, lost_started = float(m.get("hb_started_ts") or 0), float(m.get("watch_lost_started_ts") or 0)
    if started and lost_started and started - lost_started > C.REBOOT_TOLERANCE_S:
        return C.WatchMsg.APP_RESTART % (C.WatchMsg.CRASH if m.get("hb_resume_crash") else "") + (
            " " + m["hb_resume"] if m.get("hb_resume") else "")
    if boot and lost_boot:
        return C.WatchMsg.NET                     # may + app khong khoi dong lai -> mat mang / ERP khong nhan duoc


def decide(m, now, cfg, expected):
    """Viec can lam voi 1 may luc nay. expected: ham () -> expected_lives (chi goi khi may im lang).
    Tra {action, level?, title?, text?, brands?, vals?} - vals = gia tri ghi lai len may."""
    none = {"action": C.WatchAction.NONE}
    age, lost_ts = silent_s(m, now), float(m.get("watch_lost_ts") or 0)
    if age is None:
        return none
    name, last = machine_name(m), float(m["hb_last_seen_ts"])
    if age <= int(cfg.get("machine_offline_min") or C.MACHINE_OFFLINE_MIN) * 60:
        if not lost_ts:
            return none
        back = float(m.get("watch_back_ts") or 0) or last
        text = C.WatchMsg.BACK % (name, max(1, int(round((back - lost_ts) / 60.0)))) + _back_reason(m)
        return {"action": C.WatchAction.BACK, "level": C.Level.INFO, "title": C.WatchMsg.TITLE_BACK % name,
                "text": text, "brands": m.get("watch_brands") or [],
                "vals": {"watch_lost_ts": 0, "watch_back_ts": 0, "watch_sent_ts": 0}}
    if m.get("hb_state") == C.APP_STOPPING:
        return none
    lives = expected()
    if not lives:
        return none
    if lost_ts and now - float(m.get("watch_sent_ts") or 0) < repeat_minutes(now, cfg) * 60:
        return none
    text = C.WatchMsg.LOST % (name, _clock(last, now), _lives_text(lives))
    crit = [a for a in m.get("hb_alerts") or [] if a.endswith("(đỏ)")][:2]
    if crit:                                      # goi y nguyen nhan tu bao dong khan cua nhip cuoi
        text += C.WatchMsg.LAST_PROBLEMS % "; ".join(c[:-5].strip() for c in crit)
    vals = {"watch_sent_ts": now}
    if lost_ts:
        text += C.WatchMsg.STILL % int(age // 60)
    else:
        vals.update({"watch_lost_ts": last, "watch_back_ts": 0, "watch_lost_boot_ts": float(m.get("hb_boot_ts") or 0),
                     "watch_lost_started_ts": float(m.get("hb_started_ts") or 0)})
    brands = sorted({x["brand"] for x in lives if x.get("brand")})
    vals["watch_brands"] = brands
    return {"action": C.WatchAction.REMIND if lost_ts else C.WatchAction.LOST, "level": C.Level.CRIT,
            "title": C.WatchMsg.TITLE_LOST % name, "text": text, "brands": brands, "vals": vals}
