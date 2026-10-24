# Copyright (c) 2026, eCentric and contributors
"""Su co AI Live (fix10h, thuan Python): mot su co mo cho moi (may) im lang / moi (may, live, ma) bao dong app nho
ERP gui ho (forward). Nhac lai 5/15 phut khi chua xac nhan, leo thang khi KHAN chua ai xac nhan sau N phut,
"da on" khi ma bien mat khoi nhip tim (cho them 1 nhip de tranh chap chon). Thoi gian = epoch giay."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.domain import machine_watch_rules as W


def key_of(kind, machine, live="", code=""):
    return "%s|%s|%s|%s" % (kind, machine or "", live or "", code or "")


def is_open(inc):
    return bool(inc) and inc.get("status") in (C.IncStatus.OPEN, C.IncStatus.ACKED)


def forward_alerts(row):
    """Bao dong app nho ERP gui ho, dang con o nhip cuoi: {code: alert}. Chi muc vang / do (info bo qua)."""
    return {a["code"]: a for a in row.get("alerts") or []
            if a.get("src") == "app" and a.get("forward") and a.get("level") in (C.Level.WARN, C.Level.CRIT)}


def repeat_due(inc, now, cfg):
    """Nhac lai: chi KHAN, chua xac nhan, qua 5 phut (dem 15 phut) tu lan gui truoc."""
    if inc.get("status") != C.IncStatus.OPEN or inc.get("level") != C.Level.CRIT:
        return False
    return now - float(inc.get("last_sent_ts") or 0) >= W.repeat_minutes(now, cfg) * 60


def escalate_due(inc, now, cfg):
    """KHAN chua ai xac nhan sau incident_escalate_min phut (mac dinh 10) -> gui them 1 lan cho kenh leo thang."""
    if inc.get("status") != C.IncStatus.OPEN or inc.get("level") != C.Level.CRIT or float(inc.get("escalated_ts") or 0):
        return False
    start = float(inc.get("first_sent_ts") or 0) or float(inc.get("opened_ts") or now)   # tinh tu luc bao lan dau, khong tu luc mat tin
    return now - start >= int(cfg.get("incident_escalate_min") or C.INC_ESCALATE_MIN) * 60


def forward_plan(row, open_incs, now, dead_man_min):
    """Viec can lam voi bao dong forward cua 1 live. open_incs: {code: su co dang mo}.
    Tra [(viec, code, alert|None, inc|None)] - viec: new | repeat? (service xet) | missing | back_again | ok."""
    cur, out = forward_alerts(row), []
    for code, a in cur.items():
        inc = open_incs.get(code)
        if not inc:
            out.append(("new", code, a, None))
        else:
            out.append(("back_again" if float(inc.get("missing_since_ts") or 0) else "still", code, a, inc))
    alive = now - float(row.get("last_seen_ts") or 0) <= dead_man_min * 60
    for code, inc in open_incs.items():
        if code in cur or not alive:
            continue                       # may im lang: chua biet da on chua - su co may im lang lo
        miss = float(inc.get("missing_since_ts") or 0)
        if not miss:
            out.append(("missing", code, None, inc))
        elif float(row.get("last_seen_ts") or 0) > miss:
            out.append(("ok", code, None, inc))      # them it nhat 1 nhip moi van khong co ma -> da on
    return out


def minutes_since(ts, now):
    return max(1, int(round((now - float(ts or now)) / 60.0)))


def ack_suffix(inc):
    if inc.get("status") != C.IncStatus.ACKED:
        return ""
    note = (inc.get("ack_note") or "").strip()
    return C.IncMsg.ACK_NOTE % (inc.get("acked_by") or "?", (" – " + note[:120]) if note else "")


def view(inc, now):
    """Su co -> dong hien tren man Truc live / Su co."""
    end = float(inc.get("resolved_ts") or 0) or now
    return {"name": inc["name"], "kind": inc.get("kind"), "status": inc.get("status"),
            "status_text": C.INC_STATUS_TEXT.get(inc.get("status"), inc.get("status")), "level": inc.get("level"),
            "machine": inc.get("machine") or "", "live": inc.get("live") or "", "brand": inc.get("brand") or "",
            "code": inc.get("code") or "", "title": inc.get("title") or "", "text": inc.get("text") or "",
            "opened_ts": float(inc.get("opened_ts") or 0), "duration_s": int(max(0, end - float(inc.get("opened_ts") or end))),
            "sent_count": int(inc.get("sent_count") or 0), "last_sent_ts": float(inc.get("last_sent_ts") or 0),
            "acked_by": inc.get("acked_by") or "", "acked_ts": float(inc.get("acked_ts") or 0),
            "ack_note": inc.get("ack_note") or "", "escalated_ts": float(inc.get("escalated_ts") or 0),
            "resolved_ts": float(inc.get("resolved_ts") or 0), "resolve_text": inc.get("resolve_text") or ""}
