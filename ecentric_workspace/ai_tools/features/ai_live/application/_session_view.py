# Copyright (c) 2026, eCentric and contributors
"""Dung chung cho trang Phien live (thuan Python): ghep phien (ERP) + tin hieu moi nhat (app) thanh 1 dong."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.domain import health_rules as R
from ecentric_workspace.ai_tools.features.ai_live.domain import session_rules as S

STATUS_ORDER = {C.SessionStatus.PROBLEM: 0, C.SessionStatus.ON_AIR: 1, C.SessionStatus.SCHEDULED: 2, C.SessionStatus.OFF: 3}


def summarize(sess, health_row, now, cfg):
    """Dong tren danh sach: phien + trang thai + khung ke tiep + nguoi xem + chi phi hom nay."""
    ev = R.evaluate(dict(health_row, schedule=S.to_app_schedule(sess["slots"])), now, cfg) if health_row else None
    st = S.status_of(sess, health_row, ev, now, cfg["dead_man_min"])
    nxt = S.next_window(sess["slots"], now) if sess["enabled"] else None
    det = (health_row or {}).get("detail") or {}
    pf = det.get("platform") or {}
    return {"id": sess["id"], "title": sess["title"], "brand": sess["brand"], "platform": sess["platform"],
            "shop_name": sess["shop_name"], "machine": sess["machine"], "enabled": sess["enabled"], "kit": sess["kit"],
            "mode": sess["mode"], "status": st, "key": R.key_of(sess["machine"], sess["id"]) if sess["machine"] else "",
            "level": ev["level"] if ev else None,
            "reasons": [{"code": r["code"], "level": r["level"], "text": r["text"]} for r in (ev or {}).get("reasons", [])[:3]],
            "app_state": (health_row or {}).get("state") or "", "last_seen_ts": (health_row or {}).get("last_seen_ts") or 0,
            "next": {"start": nxt[0], "end": nxt[1]} if nxt else None,
            "viewers": pf.get("viewers"), "cost_today_usd": det.get("cost_today_usd"),
            "now_playing": (det.get("now") or {}).get("product") or (det.get("now") or {}).get("file") or ""}


def health_index(rows):
    return {r["key"]: r for r in rows}
