# Copyright (c) 2026, eCentric and contributors
"""App tren may phat gui lai toan bo khung gio cua 1 phien live cua chinh may do (lich 2 chieu: ERP sua qua save_slots,
app keo qua get_config.lives[].schedule). Ma live tren app = ma phien tren ERP (get_config.lives[].id).
Chuan hoa giong save_slots; DocType validate kiem tra lai trung gio + suc chua may."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common
from ecentric_workspace.ai_tools.features.ai_live.domain import session_rules as S


class PushSlotsService:
    def __init__(self, machines=None, sessions=None):
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_session as DS
        self.machines = machines or DS.machines_all()
        self.sessions = sessions or DS.sessions()

    def execute(self, user, machine, live, slots):
        m = _common.require_machine(self.machines, user, machine)
        sess = self._session_of(m, str(live or "").strip())
        raw = _common.parse_json(slots, "khung giờ") if isinstance(slots, str) else slots
        if not isinstance(raw, list):
            raise C.AiLiveError(C.SessMsg.BAD_SLOTS)          # khong tu xoa lich khi app gui thieu slots
        clean = S.norm_slots(raw)
        self.sessions.save_slots(sess["id"], clean)
        return {"session": self.sessions.get(sess["id"]), "slots": clean, "schedule": S.to_app_schedule(clean)}

    def _session_of(self, m, live):
        if not C.LIVE_RE.match(live):
            raise C.AiLiveError(C.SessMsg.BAD_ID)
        sess = next((s for s in self.sessions.by_machine(m["machine_code"]) if s["id"] == live), None)
        if not sess:
            raise C.AiLiveError(C.SessMsg.NOT_ON_MACHINE % (live, m["machine_code"]))
        if sess["brand"] and sess["brand"] not in _common.machine_brands(m):
            raise C.AiLiveError(C.SessMsg.BRAND_OFF % (sess["brand"], m["machine_code"]))
        return sess
