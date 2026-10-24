# Copyright (c) 2026, eCentric and contributors
"""Danh sach Bo live (tab Bo live tren /ai-video)."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common, _deps
from ecentric_workspace.ai_tools.features.ai_live.domain import kit_plan


class ListKitsService:
    def __init__(self, kits=None, brands=None):
        self.kits = kits or _deps.kits()
        self.brands = brands or _deps.brands()

    def execute(self, roles, brand=None):
        _common.require_role(roles, C.VIEW_ROLES, C.Msg.NEED_VIEW)
        return {"kits": self.kits.list(brand or None), "brands": self.brands.list_names(),
                "can_admin": bool(set(roles or ()) & set(C.ADMIN_ROLES)), "generic_defaults": kit_plan.generic_defaults()}
