# Copyright (c) 2026, eCentric and contributors
"""Tuong Giam sat: moi live 1 o (anh moi nhat, mau, so lieu chinh, canh bao). Loc theo brand / muc."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common
from ecentric_workspace.ai_tools.features.ai_live.application._monitor_view import bucket, tile
from ecentric_workspace.ai_tools.features.ai_live.domain import health_rules as R

#: Live khong co tin hieu qua 7 ngay va ngoai gio: an khoi tuong (may da thoi dung).
HIDE_AFTER_S = 7 * 86400
FILTERS = ("problem", C.Level.CRIT, C.Level.WARN, C.Level.OK, C.Level.IDLE)


class MonitorWallService:
    def __init__(self, health=None, alerts=None, settings=None, clock=None):
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_monitor as D
        self.health = health or D.health()
        self.alerts = alerts or D.alerts()
        self.settings = settings or D.settings()
        self.clock = clock or R.now_ts

    def execute(self, roles, brand=None, level=None):
        _common.require_role(roles, C.VIEW_ROLES, C.Msg.NEED_VIEW)
        cfg, now = self.settings.get(), self.clock()
        latest = self.alerts.latest_by_key(now - 86400)
        tiles = []
        for row in self.health.all():
            ev = R.evaluate(row, now, cfg)
            if ev["level"] == C.Level.IDLE and ev["stale_s"] > HIDE_AFTER_S:
                continue
            tiles.append(tile(row, ev, latest.get(row["key"])))
        brands = sorted({t["brand"] for t in tiles if t["brand"]})
        counts = {"total": len(tiles)}
        for lv in (C.Level.CRIT, C.Level.WARN, C.Level.OK, C.Level.IDLE):
            counts[lv] = sum(1 for t in tiles if bucket(t["level"]) == lv)
        if brand:
            tiles = [t for t in tiles if t["brand"] == brand]
        if level in FILTERS:
            want = (C.Level.CRIT, C.Level.WARN) if level == "problem" else (level,)
            tiles = [t for t in tiles if bucket(t["level"]) in want]
        tiles.sort(key=lambda t: (-C.LEVEL_RANK.get(t["level"], 0), t["brand"], t["machine"] or "", t["live"] or ""))
        return {"tiles": tiles, "counts": counts, "brands": brands, "server_time": now,
                "refresh_s": 15, "dead_man_min": cfg["dead_man_min"]}
