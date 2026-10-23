# Copyright (c) 2026, eCentric and contributors
"""Man Truc live (wallboard, B2 - fix10h; thuan Python): moi live dang chay 1 the, nhom theo may; may mat lien lac
thanh dai rieng tren dau. Mau / chu / "da X phut" deu tinh o day - JS chi hien thi. Thoi gian = epoch giay."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.domain import machine_watch_rules as W

#: muc the: lost (mat lien lac) / crit (KHAN) / warn (canh bao) / ok (dang live binh thuong)
RANK = {"lost": 0, "crit": 0, "warn": 1, "ok": 2}
MODE_TEXT = {"camera": "camera", "rtmp": "RTMP", "both": "camera + RTMP", "talk": "nói chuyện"}


def machine_lost(m, now, cfg):
    """May im lang qua nguong, khong tat app dung cach -> dai "Mat lien lac" (du chua chac co live)."""
    age = W.silent_s(m, now)
    return (age is not None and age > int(cfg.get("machine_offline_min") or C.MACHINE_OFFLINE_MIN) * 60
            and m.get("hb_state") != C.APP_STOPPING)


def card_level(ev_level, lost):
    if lost or ev_level == C.Level.OFF:
        return "lost"
    return {C.Level.CRIT: "crit", C.Level.WARN: "warn"}.get(ev_level, "ok")


def problem_of(level, ev, row, now):
    """Dong van de to nhat cua the + moc tinh "da X phut"."""
    if level == "lost":
        return {"text": "Mất liên lạc máy", "since_ts": float(row.get("last_seen_ts") or now)}
    if level in ("crit", "warn") and ev.get("reasons"):
        r = ev["reasons"][0]
        return {"text": r["text"], "since_ts": float(r.get("since") or now)}
    return None


def cost_view(usd, cap):
    usd, cap = round(float(usd or 0), 2), float(cap or 0)
    pct = int(round(usd / cap * 100)) if cap > 0 else None
    return {"usd": usd, "cap": cap, "pct": pct, "over": bool(cap and usd >= cap),
            "text": ("$%.2f / $%g (%d%%)" % (usd, cap, pct)) if cap > 0 else ("$%.2f · không đặt trần" % usd)}


def ai_text(extra, failover):
    ai = (extra or {}).get("ai") or {}
    if ai.get("mode") == "backup":
        return {"text": "AI: dự phòng" + (" (%d)" % failover if failover else ""), "tone": "warn", "label": ai.get("label") or ""}
    if ai.get("mode") == "main":
        return {"text": "AI: chính" + (" · đã chuyển %d lần" % failover if failover else ""), "tone": "ok",
                "label": ai.get("label") or ""}
    if failover:
        return {"text": "AI dự phòng %d lần trong khung" % failover, "tone": "warn", "label": ""}
    return {"text": "AI: chưa rõ (app < 1.0.21)", "tone": "idle", "label": ""}


def sort_cards(cards):
    """KHAN + mat lien lac len dau (lau nhat truoc), roi canh bao, roi dang live."""
    return sorted(cards, key=lambda c: (RANK[c["level"]], (c["problem"] or {}).get("since_ts") or 9e12,
                                        c["machine"], c["live"]))


def _ver(v):
    try:
        return tuple(int(x) for x in str(v or "").split(".")[:3])
    except ValueError:
        return ()


def missed_today(rows, airing, hb, brand=None, machine=None):
    """"Lo gio hom nay" (theo bo loc): app bao lo + khung qua 15 phut khong bao cao ma live cung khong dang len song -
    chi tinh "khong bao cao" cho may da biet gui push_slot_report (co bao cao hom nay / app >= 1.0.21)."""
    reporting = {r["report"]["machine"] for r in rows if r.get("report") and r["report"].get("machine")}
    reporting |= {c for c, m in hb.items() if _ver(m.get("hb_version")) >= (1, 0, 21)}
    n = 0
    for r in rows:
        if (brand and r.get("brand") != brand) or (machine and r.get("machine") != machine) or r["off_plan"] or r["stale_plan"]:
            continue
        if (r.get("report") or {}).get("status") == "missed":
            n += 1
        elif r["no_report"] and r["live"] not in airing and r.get("machine") in reporting:
            n += 1
    return n


LEVEL_TEXT = {"lost": "○ Mất liên lạc", "crit": "■ KHẨN", "warn": "▲ Cảnh báo", "ok": "● Đang live"}


def today_rows(rows, cards, now):
    """fix10h (Gantt "Hom nay"): moi khung ke hoach / bao cao hom nay + tinh trang that de to khoi:
    dang trong khung -> muc cua the live (lost/crit/warn/ok, chua co tin hieu -> "lost"); chua toi -> future; qua -> past.
    state = 1 dong chu cho danh sach dien thoai."""
    by_live = {c["live"]: c for c in cards}
    out = []
    for r in rows:
        c = by_live.get(r["live"])
        if r["start_ts"] > now:
            level, state = "future", "Chờ giờ"
        elif r["end_ts"] <= now:
            level = "past"
            state = " · ".join(x["text"] for x in r["chips"]) or "Đã hết khung"
        elif c:
            level = c["level"]
            state = LEVEL_TEXT[level] + (" · " + c["problem"]["text"] if c.get("problem") else "")
        else:
            level, state = "lost", "○ Đang trong giờ mà không có tín hiệu"
        out.append(dict(r, level=level, state=state, key=(c or {}).get("key") or ""))
    return out


def machine_view(m, now, cfg, cards):
    """1 dong may tren Gantt: trang thai + may chu (GPU cao nhat cua cac live tren may)."""
    lost, age = machine_lost(m, now, cfg), W.silent_s(m, now)
    if lost:
        st, pill = "○ Mất liên lạc %d phút" % int((age or 0) // 60), "p-bad"
    elif m.get("hb_state") == C.APP_STOPPING:
        st, pill = "Đã tắt app", "p-idle"
    elif m.get("hb_minimal"):
        st, pill = "▲ Tải cao", "p-warn"
    else:
        st, pill = "● Online", "p-ok"
    gpus = [c["gpu"] for c in cards if c["machine"] == m["machine_code"] and c.get("gpu") is not None]
    sub = " · ".join(x for x in ("GPU %d%%" % max(gpus) if gpus else "", "app " + m["hb_version"] if m.get("hb_version") else "") if x)
    return {"code": m["machine_code"], "label": m.get("label") or "", "status": st, "pill": pill, "sub": sub, "lost": lost}


def counters(cards, lost_machines, missed_today):
    on_air = sum(1 for c in cards if c["on_air"] and c["level"] != "lost")
    lost_lives = sum(1 for c in cards if c["level"] == "lost" and c["machine"] not in {m["machine"] for m in lost_machines})
    return {"on_air": on_air, "crit": sum(1 for c in cards if c["level"] == "crit"),
            "warn": sum(1 for c in cards if c["level"] == "warn"), "lost": len(lost_machines) + lost_lives,
            "missed_today": missed_today}
