# Copyright (c) 2026, eCentric and contributors
"""Bat / tat nhieu phien live cung luc (trang Phien live). Phien nao bat len lam may qua tai -> bao loi rieng
phien do, cac phien khac van luu."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common

MAX_BULK = 100


class SetSessionsEnabledService:
    def __init__(self, sessions=None, atomic=None):
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_session as DS
        self.sessions = sessions or DS.sessions()
        #: atomic(fn): chay fn trong savepoint, loi thi lui rieng phan do (tang API truyen vao; test: chay thang)
        self.atomic = atomic or (lambda fn: fn())

    def execute(self, roles, names, enabled):
        _common.require_role(roles, C.VIEW_ROLES, C.Msg.NEED_VIEW)
        lst = _common.parse_json(names, "danh sách phiên") if isinstance(names, str) else names
        lst = [str(n) for n in (lst or []) if C.LIVE_RE.match(str(n))][:MAX_BULK]
        done, errors = [], []
        for n in lst:
            try:
                done += self.atomic(lambda n=n: self.sessions.set_enabled([n], bool(enabled)))
            except C.AiLiveError as e:
                errors.append({"id": n, "error": str(e)})
        return {"done": done, "errors": errors, "enabled": bool(enabled)}
