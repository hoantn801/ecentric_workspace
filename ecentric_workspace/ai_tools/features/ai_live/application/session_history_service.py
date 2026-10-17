# Copyright (c) 2026, eCentric and contributors
"""Lich su phien live (tab Lich su phien + chi tiet phien): moi lan chay 1 dong, loc theo phien / brand / so ngay;
kem tong cong (so lan chay, gio live, comment, tra loi, chao, chi phi)."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common
from ecentric_workspace.ai_tools.features.ai_live.domain import health_rules as R


class SessionHistoryService:
    def __init__(self, logs=None, clock=None):
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_session as DS
        self.logs = logs or DS.logs()
        self.clock = clock or R.now_ts

    def execute(self, roles, live=None, brand=None, days=7, limit=500):
        _common.require_role(roles, C.VIEW_ROLES, C.Msg.NEED_VIEW)
        days = max(1, min(int(days or 7), C.MAX_HISTORY_DAYS))
        rows = self.logs.list(self.clock() - days * 86400, live or None, brand or None, limit)
        tot = {"runs": len(rows), "hours": round(sum(r["duration_s"] for r in rows) / 3600.0, 1),
               "cost_usd": round(sum(r["cost_usd"] for r in rows), 2)}
        for k in C.DETAIL_COUNTERS:
            tot[k] = sum(r[k] for r in rows)
        return {"rows": rows, "totals": tot, "days": days, "brands": sorted({r["brand"] for r in rows if r["brand"]})}
