# Copyright (c) 2026, eCentric and contributors
"""May phat lay lenh dang cho (token may phat). Lenh qua han -> Expired; lenh tra ve -> Sent."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common
from ecentric_workspace.ai_tools.features.ai_live.domain import health_rules as R


class PullCommandsService:
    def __init__(self, machines=None, commands=None, clock=None):
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_session as DS
        self.machines = machines or DS.machines_all()
        self.commands = commands or DS.commands()
        self.clock = clock or R.now_ts

    def execute(self, user, machine):
        m = _common.require_machine(self.machines, user, machine)
        now, out = self.clock(), []
        for c in self.commands.pending(m["machine_code"]):
            if now - c["created_ts"] > C.CMD_TTL_S:
                self.commands.set_status(c["id"], C.CMD_EXPIRED)
                continue
            if len(out) >= C.CMD_PULL_MAX:
                break
            self.commands.set_status(c["id"], C.CMD_SENT, "sent_ts", now)
            out.append({"id": c["id"], "live": c["live"], "action": c["action"], "args": c["args"],
                        "created_ts": c["created_ts"], "ttl_sec": C.CMD_TTL_S,   # fix10g: app 1.0.21 tu bo lenh qua han
                        "created_at": R.iso(c["created_ts"]), "expires_at": R.iso(c["created_ts"] + C.CMD_TTL_S)})
        return {"commands": out, "server_time": now}
