# Copyright (c) 2026, eCentric and contributors
"""Chi tiet 1 phien live: thong tin phien, lich, trang thai, dang phat / sap phat / hang cau hoi / comment gan day /
loi chao (app gui kem tin hieu), so lieu 1 gio, bao dong 24 gio, lenh da gui cho app."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common
from ecentric_workspace.ai_tools.features.ai_live.application._session_view import summarize
from ecentric_workspace.ai_tools.features.ai_live.domain import health_rules as R


class SessionDetailService:
    def __init__(self, sessions=None, health=None, samples=None, alerts=None, settings=None, commands=None, clock=None,
                 logs=None):
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_monitor as DM
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_session as DS
        self.sessions = sessions or DS.sessions()
        self.health = health or DM.health()
        self.samples = samples or DM.samples()
        self.alerts = alerts or DM.alerts()
        self.settings = settings or DM.settings()
        self.commands = commands or DS.commands()
        self.logs = logs or DS.logs()
        self.clock = clock or R.now_ts

    def execute(self, roles, name):
        _common.require_role(roles, C.VIEW_ROLES, C.Msg.NEED_VIEW)
        sess = self.sessions.get(str(name or ""))
        if not sess:
            raise C.AiLiveError(C.SessMsg.NOT_FOUND % name)
        now, cfg = self.clock(), self.settings.get()
        key = R.key_of(sess["machine"], sess["id"]) if sess["machine"] else ""
        row = self.health.get(key) if key else None
        out = summarize(sess, row, now, cfg)
        out.update({"session": sess, "server_time": now, "refresh_s": 10,
                    "detail": (row or {}).get("detail") or {}, "metrics": (row or {}).get("metrics") or {},
                    "app_version": (row or {}).get("app_version") or "",
                    "thumbs": {k: (row or {}).get(k + "_thumb_ts") or 0 for k in C.THUMB_KINDS},
                    "samples": self.samples.since(key, now - 3600) if key else [],
                    "alerts": self.alerts.for_key(key, now - 86400) if key else [],
                    "commands": self.commands.recent(sess["id"], now - 86400),
                    "history": self.logs.list(now - 30 * 86400, sess["id"], None, 10)})
        return out
