# Copyright (c) 2026, eCentric and contributors
"""Chi tiet 1 live tren man Giam sat: so lieu 1 gio gan nhat (ve bieu do) + lich su bao dong 24 gio."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common
from ecentric_workspace.ai_tools.features.ai_live.application._monitor_view import tile
from ecentric_workspace.ai_tools.features.ai_live.domain import health_rules as R


class MonitorDetailService:
    def __init__(self, health=None, samples=None, alerts=None, settings=None, clock=None):
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_monitor as D
        self.health = health or D.health()
        self.samples = samples or D.samples()
        self.alerts = alerts or D.alerts()
        self.settings = settings or D.settings()
        self.clock = clock or R.now_ts

    def execute(self, roles, key):
        _common.require_role(roles, C.VIEW_ROLES, C.Msg.NEED_VIEW)
        row = self.health.get(str(key or ""))
        if not row:
            raise C.AiLiveError(C.MonMsg.NO_KEY % key)
        now = self.clock()
        ev = R.evaluate(row, now, self.settings.get())
        hist = self.alerts.for_key(row["key"], now - 86400)
        out = tile(row, ev, hist[0] if hist else None)
        out.update({"samples": self.samples.since(row["key"], now - 3600), "alerts": hist,
                    "schedule": row.get("schedule") or [], "server_time": now,
                    "faq": (row.get("extra") or {}).get("faq") or []})      # fix10h: chon FAQ cho lenh "Phat FAQ"
        return out
