# Copyright (c) 2026, eCentric and contributors
"""18/11: luu ngan "Sua phien" tren /ai-live. Moi o cua phien vao BAN NHAP (app nhan khi Phat hanh) - xem SaveDraftService.
Rieng "Dang dung" ap ngay (giong nut bat / tat tren danh sach phien)."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common
from ecentric_workspace.ai_tools.features.ai_live.application import _session_form as SF
from ecentric_workspace.ai_tools.features.ai_live.application.save_draft_service import SaveDraftService
from ecentric_workspace.ai_tools.features.ai_live.domain import session_form_rules as F


class UpdateSessionService:
    def __init__(self, sessions=None, machines=None, kits=None, clock=None, draft=None):
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_session as DS
        self.sessions = sessions or DS.sessions()
        self.draft = draft or SaveDraftService(self.sessions, machines, clock, kits)

    def execute(self, user, roles, name, form):
        _common.require_role(roles, C.SCHEDULE_EDIT_ROLES, C.Msg.NEED_SCHEDULE_EDIT)
        form = SF.parse(form)
        sess = self.sessions.get(str(name or ""))
        if not sess:
            raise C.AiLiveError(C.SessMsg.NOT_FOUND % name)
        out = self.draft.execute(user, roles, sess["id"], slots=form.get("slots"),
                                 lc_open_before_min=form.get("lc_open_before_min") if "lc_open_before_min" in form else None,
                                 fields={k: form[k] for k in form if k not in ("slots", "lc_open_before_min", "enabled")})
        if "enabled" in form:
            on = str(form["enabled"]).strip() not in ("0", "false", "False", "")
            if on != bool(int(sess.get("enabled") or 0)):
                try:
                    self.sessions.set_enabled([sess["id"]], on)
                except C.AiLiveError as e:
                    F.fail("enabled", str(e))
                out = SF.result(self.sessions.get(sess["id"]))
        return out
