# Copyright (c) 2026, eCentric and contributors
"""Tong chi phi AI Live theo brand / ngay cho trang ERP."""
import datetime

from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common


class CostSummaryService:
    def __init__(self, costs=None, brands=None, today=None):
        if costs is None:
            from ecentric_workspace.ai_tools.features.ai_live.repositories.cost_log_repository import CostLogRepository
            costs = CostLogRepository()
        if brands is None:
            from ecentric_workspace.ai_tools.features.ai_live.repositories.brand_config_repository import BrandConfigRepository
            brands = BrandConfigRepository()
        self.costs, self.brands = costs, brands
        self.today = today or datetime.date.today

    def execute(self, roles, brand=None, days=7):
        _common.require_role(roles, C.VIEW_ROLES, C.Msg.NEED_VIEW)
        days = max(1, min(int(days or 7), 92))
        if brand and not C.BRAND_RE.match(brand):
            raise C.AiLiveError(C.Msg.BAD_BRAND % brand)
        since = (self.today() - datetime.timedelta(days=days - 1)).isoformat()
        rows = self.costs.summary(since, brand or None)
        caps = {}
        for b in {r["brand"] for r in rows}:
            caps[b] = float((self.brands.get(b) or {}).get("daily_cost_cap_usd") or 0)
        for r in rows:
            cap = caps.get(r["brand"]) or 0
            r["cap_usd"] = cap
            r["over_cap"] = bool(cap and r["usd"] >= cap)
        return {"since": since, "rows": rows, "total_usd": round(sum(r["usd"] for r in rows), 4)}
