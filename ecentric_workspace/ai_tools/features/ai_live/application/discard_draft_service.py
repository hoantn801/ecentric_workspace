# Copyright (c) 2026, eCentric and contributors
"""fix10g: bo ban nhap lich cua cac phien (rong = moi ban nhap). Lich dang phat hanh giu nguyen."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common
from ecentric_workspace.ai_tools.features.ai_live.domain import health_rules as R


class DiscardDraftService:
    def __init__(self, sessions=None, clock=None):
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_session as DS
        self.sessions = sessions or DS.sessions()
        self.clock = clock or R.now_ts

    def execute(self, user, roles, names=None):
        _common.require_role(roles, C.VIEW_ROLES, C.Msg.NEED_VIEW)
        ids = _common.id_list(names)
        done = []
        for s in self.sessions.list():
            if s.get("draft") and (not ids or s["id"] in ids):
                self.sessions.save_draft(s["id"], None, 0, user, self.clock())
                done.append(s["id"])
        return {"discarded": done}
