# Copyright (c) 2026, eCentric and contributors
"""Trang chi tiet phien -> xep 1 lenh cho app tren may phat (tam dung / tiep tuc AI, bo clip dang phat, phat FAQ ngay,
bat dau / dung dua vit).
App hoi pull_commands khoang 10 s/lan; lenh qua CMD_TTL_S chua lay thi het han."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common
from ecentric_workspace.ai_tools.features.ai_live.domain import health_rules as R


class QueueCommandService:
    def __init__(self, sessions=None, commands=None, clock=None):
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_session as DS
        self.sessions = sessions or DS.sessions()
        self.commands = commands or DS.commands()
        self.clock = clock or R.now_ts

    def execute(self, user, roles, name, action, args=None):
        _common.require_role(roles, C.VIEW_ROLES, C.Msg.NEED_VIEW)
        sess = self.sessions.get(str(name or ""))
        if not sess:
            raise C.AiLiveError(C.SessMsg.NOT_FOUND % name)
        if not sess["machine"]:
            raise C.AiLiveError(C.SessMsg.NO_MACHINE)
        if action not in C.CMD_ACTIONS:
            raise C.AiLiveError(C.SessMsg.BAD_CMD)
        clean = _clean_args(action, args)
        cid = self.commands.insert({"live": sess["id"], "machine": sess["machine"], "action": action, "args": clean,
                                    "created_ts": self.clock(), "requested_by": user})
        return {"id": cid, "status": C.CMD_QUEUED}

    def execute_wall(self, user, roles, machine, live, action, args=None, machines=None):
        """fix10h - lenh 1 cham tu man Truc live: theo (may, live) dang chay tren may (ca live khong co tren ERP)."""
        _common.require_role(roles, C.VIEW_ROLES, C.Msg.NEED_VIEW)
        if action not in C.WALL_ACTIONS:
            raise C.AiLiveError(C.SessMsg.BAD_CMD)
        live = str(live or "")
        if not C.LIVE_RE.match(live):
            raise C.AiLiveError(C.SessMsg.BAD_ID)
        if machines is None:
            from ecentric_workspace.ai_tools.features.ai_live.application import _deps_monitor as D
            machines = D.machines()
        if not machines.get(str(machine or "")):
            raise C.AiLiveError(C.SessMsg.NO_MACHINE)
        cid = self.commands.insert({"live": live, "machine": str(machine), "action": action, "args": _clean_args(action, args),
                                    "created_ts": self.clock(), "requested_by": user})
        return {"id": cid, "status": C.CMD_QUEUED}


class CommandStatusService:
    """fix10h: trang thai cac lenh vua gui (nut tren the Truc live: Dang gui -> May da nhan / Xong / Loi)."""

    def __init__(self, commands=None):
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_session as DS
        self.commands = commands or DS.commands()

    def execute(self, roles, ids):
        _common.require_role(roles, C.VIEW_ROLES, C.Msg.NEED_VIEW)
        return {"commands": [{"id": c["id"], "action": c["action"], "status": c["status"], "result": c["result"]}
                             for c in self.commands.many(_common.id_list(ids))]}


def _clean_args(action, args):
    a = _common.parse_json(args, "tham số") if isinstance(args, str) else (args or {})
    clean = {}
    if action == "play_faq":
        topic = str((a or {}).get("topic") or "").strip()[:C.MAX_CMD_ARG]
        if not topic:
            raise C.AiLiveError(C.SessMsg.BAD_CMD)
        clean["topic"] = topic
    elif action == "start_race":                 # fix10e: tham so tuy chon, ghi de 1 lan tren app
        from ecentric_workspace.ai_tools.features.ai_live.domain import race_rules as RR
        clean = RR.start_args(a)
    return clean
