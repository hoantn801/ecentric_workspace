# Copyright (c) 2026, eCentric and contributors
"""Luu toan bo khung gio cua 1 phien (tu man Lich live: keo tao / keo doi / xoa / chep tuan).
Kiem tra som cho thong bao de hieu; DocType validate kiem tra lai trung gio + suc chua may."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common
from ecentric_workspace.ai_tools.features.ai_live.domain import session_rules as S


class SaveSlotsService:
    def __init__(self, sessions=None):
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_session as DS
        self.sessions = sessions or DS.sessions()

    def execute(self, roles, name, slots):
        _common.require_role(roles, C.VIEW_ROLES, C.Msg.NEED_VIEW)
        sess = self.sessions.get(str(name or ""))
        if not sess:
            raise C.AiLiveError(C.SessMsg.NOT_FOUND % name)
        raw = _common.parse_json(slots, "khung giờ") if isinstance(slots, str) else slots
        clean = S.norm_slots(raw if isinstance(raw, list) else [])
        self.sessions.save_slots(sess["id"], clean)
        return {"session": self.sessions.get(sess["id"])}
