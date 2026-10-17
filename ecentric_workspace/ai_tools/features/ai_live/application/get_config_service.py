# Copyright (c) 2026, eCentric and contributors
"""May phat lay cau hinh cac brand duoc giao (khoa, GPU, che do, mau cau, playlist, cooldown)."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common


class GetConfigService:
    def __init__(self, machines=None, brands=None, sessions=None):
        if machines is None:
            from ecentric_workspace.ai_tools.features.ai_live.repositories.machine_repository import MachineRepository
            machines = MachineRepository()
        if brands is None:
            from ecentric_workspace.ai_tools.features.ai_live.repositories.brand_config_repository import BrandConfigRepository
            brands = BrandConfigRepository()
        self.machines, self.brands, self._sessions = machines, brands, sessions

    def execute(self, user, machine):
        m = _common.require_machine(self.machines, user, machine)
        out = []
        for b in _common.machine_brands(m):
            cfg = self.brands.get(b, with_keys=True)
            if cfg and cfg.get("enabled"):
                out.append(self._row(cfg))
        return {"machine": m["machine_code"], "label": m.get("label") or "", "brands": out,
                "max_lives": int(m.get("max_lives") or C.DEFAULT_MAX_LIVES), "lives": self._lives(m, out)}

    def _lives(self, m, brand_rows):
        """fix10d: cac phien live giao cho may nay (dang bat) - nguon goc la ERP (trang Phien live / Lich live)."""
        if self._sessions is None:
            from ecentric_workspace.ai_tools.features.ai_live.application import _deps_session as DS
            self._sessions = DS.sessions()
        from ecentric_workspace.ai_tools.features.ai_live.domain import session_rules as S
        modes = {r["brand"]: r["mode"] for r in brand_rows}
        return [{"id": s["id"], "title": s["title"], "brand": s["brand"], "platform": s["platform"],
                 "shop_name": s["shop_name"], "tiktok_username": s["tiktok_username"], "obs_port": s["obs_port"] or None,
                 "kit": s["kit"], "mode": s["mode"] or modes.get(s["brand"]) or "full", "mode_override": s["mode"] or "",
                 "auto_obs_start": bool(s["auto_obs_start"]), "schedule": S.to_app_schedule(s["slots"]),
                 "watch_url": s.get("watch_url") or "", "phone_serial": s.get("phone_serial") or "",
                 "updated_at": s["updated_at"]}
                for s in self._sessions.by_machine(m["machine_code"]) if s["enabled"]]

    def _row(self, cfg):
        row = {"brand": cfg["brand"], "brand_name": cfg.get("brand_name") or cfg["brand"],
               "gpu_url": cfg.get("gpu_url") or "", "mode": cfg.get("mode") or "full",
               "break_sec": int(cfg.get("break_sec") or C.DEFAULT_BREAK_SEC), "kit_folder": cfg.get("kit_folder") or "",
               "minimax_group": cfg.get("minimax_group") or "",
               "shopee_partner_id": str(cfg.get("shopee_partner_id") or ""), "shopee_shop_id": str(cfg.get("shopee_shop_id") or ""),
               "daily_cost_cap_usd": float(cfg.get("daily_cost_cap_usd") or 0), "updated_at": cfg.get("updated_at") or ""}
        for f in C.KEY_FIELDS:
            row[f] = cfg.get(f) or ""
        for out_key, field in C.SETTING_FIELDS.items():
            try:
                row[out_key] = _common.parse_json(cfg.get(field), out_key)
            except C.AiLiveError:
                row[out_key] = None              # du lieu hong tren ERP khong lam may phat dung
        return row
