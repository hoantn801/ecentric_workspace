# Copyright (c) 2026, eCentric and contributors
"""fix10g: bo ban nhap lich cua cac phien (rong = moi ban nhap). Lich dang phat hanh giu nguyen.
18/11: phien moi tao chua phat hanh thi khong bo nhap (bo qua khi bo tat ca, bao loi khi chi dinh)."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common
from ecentric_workspace.ai_tools.features.ai_live.domain import health_rules as R
from ecentric_workspace.ai_tools.features.ai_live.domain import schedule_rules as P


class DiscardDraftService:
    def __init__(self, sessions=None, clock=None):
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_session as DS
        self.sessions = sessions or DS.sessions()
        self.clock = clock or R.now_ts

    def execute(self, user, roles, names=None):
        _common.require_role(roles, C.SCHEDULE_EDIT_ROLES, C.Msg.NEED_SCHEDULE_EDIT)
        ids = _common.id_list(names)
        done = []
        for s in self.sessions.list():
            if P.is_new(s):         # 18/11: phien chua phat hanh - nhap la toan bo phien, khong bo duoc
                if s["id"] in ids:
                    raise C.AiLiveError(C.SessMsg.NEW_NO_DISCARD % (s.get("title") or s["id"]))
                continue
            if s.get("draft") and (not ids or s["id"] in ids):
                self.sessions.save_draft(s["id"], None, 0, user, self.clock())
                done.append(s["id"])
        return {"discarded": done}
