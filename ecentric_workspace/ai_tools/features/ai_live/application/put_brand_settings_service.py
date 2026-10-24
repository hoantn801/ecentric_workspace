# Copyright (c) 2026, eCentric and contributors
"""App sua mau cau / playlist / cooldown cua brand -> ghi len ERP de moi may live brand do cung nhan."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common


class PutBrandSettingsService:
    def __init__(self, machines=None, brands=None):
        if machines is None:
            from ecentric_workspace.ai_tools.features.ai_live.repositories.machine_repository import MachineRepository
            machines = MachineRepository()
        if brands is None:
            from ecentric_workspace.ai_tools.features.ai_live.repositories.brand_config_repository import BrandConfigRepository
            brands = BrandConfigRepository()
        self.machines, self.brands = machines, brands

    def execute(self, user, roles, payload):
        import json
        p = payload if isinstance(payload, dict) else (_common.parse_json(payload, "cài đặt") or {})
        brand = str(p.get("brand") or "")
        if set(roles or ()) & set(C.ADMIN_ROLES):
            pass                                  # quan tri sua moi brand
        else:
            m = _common.require_machine(self.machines, user)
            if brand not in _common.machine_brands(m):
                raise C.AiLivePermission(C.Msg.BRAND_NOT_ALLOWED % brand)
        if not self.brands.get(brand):
            raise C.AiLiveError(C.Msg.UNKNOWN_BRAND % brand)
        values = {}
        for key, field in C.SETTING_FIELDS.items():
            if key in p and p[key] is not None:
                val = _common.parse_json(p[key], key)
                values[field] = json.dumps(val, ensure_ascii=False)
        if not values:
            return {"saved": False, "updated_at": None}
        return {"saved": True, "updated_at": self.brands.set_settings(brand, values)}
