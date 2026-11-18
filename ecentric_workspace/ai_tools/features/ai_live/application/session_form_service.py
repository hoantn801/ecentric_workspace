# Copyright (c) 2026, eCentric and contributors
"""18/11: du lieu cho ngan Tao / Sua phien tren /ai-live - may phat (brand duoc giao, dang mo hay tat), bo live, che do;
khi sua: phien + ban nhap hien tai. live_options(): cac live may da bao (o "Live tren may", live da co phien thi xam)."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common
from ecentric_workspace.ai_tools.features.ai_live.domain import health_rules as R
from ecentric_workspace.ai_tools.features.ai_live.domain import schedule_rules as P
from ecentric_workspace.ai_tools.features.ai_live.domain import session_form_rules as F


class SessionFormService:
    def __init__(self, sessions=None, machines=None, kits=None, health=None, clock=None):
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_monitor as DM
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_session as DS
        self.sessions = sessions or DS.sessions()
        self.machines = machines or DS.machines_all()
        self.kits = kits or DS.kits()
        self.health = health or DM.health()
        self.clock = clock or R.now_ts

    def execute(self, roles, name=None):
        _common.require_role(roles, C.SCHEDULE_EDIT_ROLES, C.Msg.NEED_SCHEDULE_EDIT)
        now = self.clock()
        out = {"machines": [self._machine(m, now) for m in self.machines.sync_states() if m.get("enabled")],
               "kits": [{"name": k["name"], "title": k.get("title") or k["name"], "brand": k.get("brand") or ""}
                        for k in self.kits.list(limit=200)],
               "platforms": list(C.PLATFORMS), "modes": list(C.MODES), "open_before_hint": C.DEFAULT_OPEN_BEFORE_HINT,
               "open_before_range": list(C.OPEN_BEFORE_RANGE), "server_time": now, "session": None}
        if name:
            s = self.sessions.get(str(name))
            if not s:
                raise C.AiLiveError(C.SessMsg.NOT_FOUND % name)
            v = P.draft_view(s)
            out["session"] = dict({k: v.get(k) for k in P.VIEW_KEYS}, id=s["id"], live_id=s["live"], enabled=s["enabled"],
                                  unpublished=P.is_new(s), has_draft=bool(s.get("draft")), state=P.draft_state(s),
                                  warning=F.tiktok_warning(v.get("platform"), v.get("tiktok_username")))
        return out

    def live_options(self, roles, machine):
        _common.require_role(roles, C.SCHEDULE_EDIT_ROLES, C.Msg.NEED_SCHEDULE_EDIT)
        code, now = F.text(machine), self.clock()
        m = self.machines.get(code) if code else None
        if not m:
            F.fail("machine", C.SessMsg.MACHINE_UNKNOWN % code if code else C.SessMsg.NEED_MACHINE)
        info = self._machine(m, now)
        taken = {s["live"]: s for s in self.sessions.by_machine(code)}
        lives = []
        for x in F.machine_lives(m.get("hb_known_lives"), self.health.all(), code, now, C.KNOWN_LIVE_KEEP_S):
            s = taken.get(x["live"])
            lives.append(dict(x, label=F.live_label(x), taken=bool(s), session=(s or {}).get("id") or "",
                              session_title=(s or {}).get("title") or ""))
        msg = C.SessMsg.NO_LIVES if not lives else ("" if info["online"] else C.SessMsg.OFFLINE_LIVES)
        return dict(info, lives=lives, message=msg)

    @staticmethod
    def _machine(m, now):
        seen = float(m.get("hb_last_seen_ts") or 0)
        return {"code": m["machine_code"], "label": m.get("label") or "", "brands": F.machine_brands(m),
                "max_lives": int(m.get("max_lives") or C.DEFAULT_MAX_LIVES), "last_seen_ts": seen,
                "online": bool(seen) and now - seen <= C.MACHINE_ONLINE_S}
