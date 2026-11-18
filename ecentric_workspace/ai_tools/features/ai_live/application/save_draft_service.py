# Copyright (c) 2026, eCentric and contributors
"""fix10g: sua lich tren ERP -> chi vao BAN NHAP cua phien (khung gio, may, kenh OBS; 18/11: mo tab truoc gio live). App chi nhan khi phat hanh.
Kiem som: khung hop le, khong trung trong phien, may ton tai + brand da giao. Suc chua may kiem khi phat hanh.
Nhap giong het ban dang phat hanh -> tu xoa nhap."""
from datetime import datetime

from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common
from ecentric_workspace.ai_tools.features.ai_live.domain import health_rules as R
from ecentric_workspace.ai_tools.features.ai_live.domain import schedule_rules as P
from ecentric_workspace.ai_tools.features.ai_live.domain import session_rules as S


class SaveDraftService:
    def __init__(self, sessions=None, machines=None, clock=None):
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_session as DS
        self.sessions = sessions or DS.sessions()
        self.machines = machines or DS.machines_all()
        self.clock = clock or R.now_ts

    def execute(self, user, roles, name, slots=None, machine=None, obs_port=None, lc_open_before_min=None):
        _common.require_role(roles, C.SCHEDULE_EDIT_ROLES, C.Msg.NEED_SCHEDULE_EDIT)
        sess = self.sessions.get(str(name or ""))
        if not sess:
            raise C.AiLiveError(C.SessMsg.NOT_FOUND % name)
        now = self.clock()
        view = P.draft_view(sess)
        if slots is not None:
            raw = _common.parse_json(slots, "khung giờ") if isinstance(slots, str) else slots
            view["slots"] = S.norm_slots(raw if isinstance(raw, list) else [])
            clash = S.self_overlap(view["slots"], datetime.fromtimestamp(now, R._VN).date())
            if clash:
                raise C.AiLiveError(C.SessMsg.SLOT_OVERLAP % (clash[1], clash[0]))
        if machine is not None:
            view["machine"] = self._machine(sess, str(machine or "").strip())
        if obs_port is not None:
            port = int(obs_port or 0)
            if port and not (C.OBS_PORT_RANGE[0] <= port <= C.OBS_PORT_RANGE[1]):
                raise C.AiLiveError(C.SessMsg.BAD_PORT)
            view["obs_port"] = port
        if lc_open_before_min is not None:      # "" = xoa (theo cai dat tren app)
            view["lc_open_before_min"] = self._open_before(lc_open_before_min)
        pub = P.published_view(sess)
        if P.same(view, pub):
            self.sessions.save_draft(sess["id"], None, 0, user, now)
        else:
            draft = P.draft_of(view, pub)
            base = sess["draft_base_version"] if sess.get("draft") else sess.get("published_version") or 0
            self.sessions.save_draft(sess["id"], draft, base, user, now)
        out = self.sessions.get(sess["id"])
        return {"session": out, "state": P.draft_state(out), "diff": P.diff_texts(pub, P.draft_view(out))}

    @staticmethod
    def _open_before(v):
        txt = str(v).strip()
        if txt == "":
            return None
        try:
            n = int(float(txt))
        except ValueError:
            raise C.AiLiveError(C.SessMsg.BAD_OPEN_BEFORE)
        if n != float(txt) or not (C.OPEN_BEFORE_RANGE[0] <= n <= C.OPEN_BEFORE_RANGE[1]):
            raise C.AiLiveError(C.SessMsg.BAD_OPEN_BEFORE)
        return n

    def _machine(self, sess, code):
        if not code:
            return ""
        m = self.machines.get(code)
        if not m:
            raise C.AiLiveError(C.SessMsg.NO_MACHINE)
        if sess["brand"] and sess["brand"] not in _common.machine_brands(m):
            raise C.AiLiveError(C.SessMsg.BRAND_OFF % (sess["brand"], code))
        return code
