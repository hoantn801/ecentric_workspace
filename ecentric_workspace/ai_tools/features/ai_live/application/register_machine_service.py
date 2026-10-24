# Copyright (c) 2026, eCentric and contributors
"""Quan tri tao/sua may phat va cap token moi (token chi hien 1 lan, dan vao app tren may phat)."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common


class RegisterMachineService:
    def __init__(self, machines=None, brands=None):
        if machines is None:
            from ecentric_workspace.ai_tools.features.ai_live.repositories.machine_repository import MachineRepository
            machines = MachineRepository()
        if brands is None:
            from ecentric_workspace.ai_tools.features.ai_live.repositories.brand_config_repository import BrandConfigRepository
            brands = BrandConfigRepository()
        self.machines, self.brands = machines, brands

    def execute(self, roles, code, label=None, brands=None, new_token=True):
        _common.require_role(roles, C.ADMIN_ROLES, C.Msg.NEED_ADMIN)
        code = str(code or "").strip()
        if not C.MACHINE_RE.match(code):
            raise C.AiLiveError(C.Msg.BAD_MACHINE)
        blist = None
        if brands is not None:
            blist = _common.machine_brands({"brands": brands})
            known = set(self.brands.list_names())
            for b in blist:
                if b not in known:
                    raise C.AiLiveError(C.Msg.UNKNOWN_BRAND % b)
        self.machines.upsert(code, None if label is None else str(label)[:140],
                             None if blist is None else "\n".join(blist))
        user = self.machines.ensure_user(code)
        token = self.machines.rotate_keys(user) if new_token else None
        return {"machine": code, "user": user, "token": token}
