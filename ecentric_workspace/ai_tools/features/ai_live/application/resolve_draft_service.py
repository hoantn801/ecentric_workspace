# Copyright (c) 2026, eCentric and contributors
"""fix10g: ban nhap "lech" (phien vua duoc app / nguoi khac phat hanh ban moi sau khi nhap) -> nguoi sua chon:
keep=1 giu ban nhap cua minh (dua moc len ban moi nhat, phat hanh se ghi de); keep=0 bo nhap, theo ban moi."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common
from ecentric_workspace.ai_tools.features.ai_live.domain import health_rules as R
from ecentric_workspace.ai_tools.features.ai_live.domain import schedule_rules as P


class ResolveDraftService:
    def __init__(self, sessions=None, clock=None):
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_session as DS
        self.sessions = sessions or DS.sessions()
        self.clock = clock or R.now_ts

    def execute(self, user, roles, name, keep):
        _common.require_role(roles, C.VIEW_ROLES, C.Msg.NEED_VIEW)
        s = self.sessions.get(str(name or ""))
        if not s:
            raise C.AiLiveError(C.SessMsg.NOT_FOUND % name)
        if not s.get("draft"):
            raise C.AiLiveError(C.PubMsg.NO_DRAFT)
        pub = P.published_view(s)
        view = P.draft_view(s)
        if keep and not P.same(view, pub):
            draft = {k: view[k] for k in ("slots", "machine", "obs_port") if view[k] != pub[k]}
            self.sessions.save_draft(s["id"], draft, s.get("published_version") or 0, user, self.clock())
        else:
            self.sessions.save_draft(s["id"], None, 0, user, self.clock())
        out = self.sessions.get(s["id"])
        return {"session": out, "state": P.draft_state(out)}
