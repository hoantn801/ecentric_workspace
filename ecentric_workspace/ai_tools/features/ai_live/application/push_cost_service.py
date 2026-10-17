# Copyright (c) 2026, eCentric and contributors
"""May phat gui chi phi AI luy ke cua 1 phien trong ngay; tra tong ngay cua brand (moi may) va tran."""
import hashlib
import json

from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common


class PushCostService:
    def __init__(self, machines=None, costs=None, brands=None):
        if machines is None:
            from ecentric_workspace.ai_tools.features.ai_live.repositories.machine_repository import MachineRepository
            machines = MachineRepository()
        if costs is None:
            from ecentric_workspace.ai_tools.features.ai_live.repositories.cost_log_repository import CostLogRepository
            costs = CostLogRepository()
        if brands is None:
            from ecentric_workspace.ai_tools.features.ai_live.repositories.brand_config_repository import BrandConfigRepository
            brands = BrandConfigRepository()
        self.machines, self.costs, self.brands = machines, costs, brands

    def execute(self, user, payload):
        p = payload if isinstance(payload, dict) else (_common.parse_json(payload, "chi phí") or {})
        m = _common.require_machine(self.machines, user, p.get("machine"))
        brand = str(p.get("brand") or "")
        if brand not in _common.machine_brands(m):
            raise C.AiLivePermission(C.Msg.BRAND_NOT_ALLOWED % brand)
        session, date = str(p.get("session") or ""), str(p.get("date") or "")
        if not C.SESSION_RE.match(session):
            raise C.AiLiveError(C.Msg.BAD_COST % "session")
        if not C.DATE_RE.match(date):
            raise C.AiLiveError(C.Msg.BAD_COST % "date")
        usd = self._usd(p.get("usd"), "usd")
        items = self._items(p.get("items"))
        key = hashlib.sha1(("%s|%s|%s|%s" % (m["machine_code"], brand, session, date)).encode()).hexdigest()[:20]
        self.costs.upsert(key, {"machine": m["machine_code"], "brand": brand, "session": session, "date": date,
                                "usd": usd, "items_json": json.dumps(items, ensure_ascii=False)})
        total = self.costs.day_total(brand, date)
        cfg = self.brands.get(brand) or {}
        cap = float(cfg.get("daily_cost_cap_usd") or 0)
        return {"saved": True, "brand_day_usd": round(total, 4), "daily_cost_cap_usd": cap,
                "over_cap": bool(cap and total >= cap)}

    def _usd(self, v, label):
        try:
            v = float(v)
        except (TypeError, ValueError):
            raise C.AiLiveError(C.Msg.BAD_COST % label)
        if v < 0 or v > C.MAX_USD or v != v:
            raise C.AiLiveError(C.Msg.BAD_COST % label)
        return round(v, 6)

    def _items(self, items):
        if items is None:
            return []
        if not isinstance(items, list) or len(items) > C.MAX_COST_ITEMS:
            raise C.AiLiveError(C.Msg.BAD_COST % "items")
        out = []
        for it in items:
            if not isinstance(it, dict):
                raise C.AiLiveError(C.Msg.BAD_COST % "items")
            out.append({"kind": str(it.get("kind") or "")[:40], "usd": self._usd(it.get("usd") or 0, "items.usd"),
                        "n": int(it.get("n") or 0)})
        return out
