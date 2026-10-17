# Copyright (c) 2026, eCentric and contributors
"""May phat lay cau hinh cac brand duoc giao (khoa, GPU, che do, mau cau, playlist, cooldown)."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common


class GetConfigService:
    def __init__(self, machines=None, brands=None):
        if machines is None:
            from ecentric_workspace.ai_tools.features.ai_live.repositories.machine_repository import MachineRepository
            machines = MachineRepository()
        if brands is None:
            from ecentric_workspace.ai_tools.features.ai_live.repositories.brand_config_repository import BrandConfigRepository
            brands = BrandConfigRepository()
        self.machines, self.brands = machines, brands

    def execute(self, user, machine):
        m = _common.require_machine(self.machines, user, machine)
        out = []
        for b in _common.machine_brands(m):
            cfg = self.brands.get(b, with_keys=True)
            if cfg and cfg.get("enabled"):
                out.append(self._row(cfg))
        return {"machine": m["machine_code"], "label": m.get("label") or "", "brands": out}

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
