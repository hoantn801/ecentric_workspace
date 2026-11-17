# Copyright (c) 2026, eCentric and contributors
"""18/11 (hop dong lich live muc 8): bat / tat NHIEU khung gio mot luc (co the cua nhieu phien) - vao BAN NHAP
cua tung phien (app nhan khi Phat hanh), giong moi sua doi lich tren ERP.
Moi muc: {session, slot (chi so trong ban nhap), key (slot_key luc trang tai)} -> lech key = khung da doi o noi khac
-> bo qua phien do, bao "tai lai" (khong bat / tat nham khung). Bat lai khung co the gay trung gio trong phien ->
phien do bao loi, phien khac van luu. Khung tat khong gui xuong may, khong tinh trung gio / suc chua."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common
from ecentric_workspace.ai_tools.features.ai_live.application.save_draft_service import SaveDraftService
from ecentric_workspace.ai_tools.features.ai_live.domain import schedule_rules as P
from ecentric_workspace.ai_tools.features.ai_live.domain import session_rules as S


class ToggleSlotsService:
    def __init__(self, sessions=None, machines=None, clock=None, draft=None):
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_session as DS
        self.sessions = sessions or DS.sessions()
        self.draft = draft or SaveDraftService(self.sessions, machines, clock)

    def execute(self, user, roles, items, enabled):
        _common.require_role(roles, C.SCHEDULE_EDIT_ROLES, C.Msg.NEED_SCHEDULE_EDIT)
        raw = _common.parse_json(items, "khung giờ") if isinstance(items, str) else items
        if not isinstance(raw, list) or not raw:
            raise C.AiLiveError(C.SessMsg.PICK_SLOTS)
        if len(raw) > C.MAX_TOGGLE_SLOTS:
            raise C.AiLiveError(C.SessMsg.TOO_MANY_SLOTS % C.MAX_TOGGLE_SLOTS)
        groups = {}
        for it in raw:
            it = it if isinstance(it, dict) else {}
            try:
                idx = int(it.get("slot"))
            except (TypeError, ValueError):
                raise C.AiLiveError(C.SessMsg.PICK_SLOTS)
            groups.setdefault(str(it.get("session") or ""), {})[idx] = str(it.get("key") or "")
        on, done, errors = bool(enabled), 0, []
        for sid, picks in groups.items():
            sess = self.sessions.get(sid)
            if not sess:
                errors.append({"session": sid, "title": sid, "error": C.SessMsg.NOT_FOUND % sid})
                continue
            slots = [dict(s) for s in P.draft_view(sess)["slots"]]
            if any(i < 0 or i >= len(slots) or S.slot_key(slots[i]) != k for i, k in picks.items()):
                errors.append({"session": sid, "title": sess.get("title") or sid, "error": C.SessMsg.SLOT_MOVED})
                continue
            changed = [i for i in picks if S.slot_on(slots[i]) != on]
            if not changed:
                continue
            for i in changed:
                slots[i]["enabled"] = on
            try:
                self.draft.execute(user, roles, sid, slots=slots)
                done += len(changed)
            except C.AiLiveError as e:
                errors.append({"session": sid, "title": sess.get("title") or sid, "error": str(e)})
        return {"changed": done, "enabled": on, "errors": errors}
