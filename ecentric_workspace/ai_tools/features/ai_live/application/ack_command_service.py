# Copyright (c) 2026, eCentric and contributors
"""May phat bao ket qua 1 lenh: Done / Failed (+ ly do ngan). Chi may duoc giao lenh moi bao duoc."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common
from ecentric_workspace.ai_tools.features.ai_live.domain import health_rules as R


class AckCommandService:
    def __init__(self, machines=None, commands=None, clock=None):
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_session as DS
        self.machines = machines or DS.machines_all()
        self.commands = commands or DS.commands()
        self.clock = clock or R.now_ts

    def execute(self, user, machine, cid, ok, result=None):
        m = _common.require_machine(self.machines, user, machine)
        c = self.commands.get(str(cid or ""))
        if not c:
            raise C.AiLiveError(C.SessMsg.CMD_NOT_FOUND % cid)
        if c["machine"] != m["machine_code"]:
            raise C.AiLivePermission(C.Msg.WRONG_MACHINE)
        status = C.CMD_DONE if ok else C.CMD_FAILED
        self.commands.set_status(c["id"], status, "done_ts", self.clock(), result or "")
        return {"id": c["id"], "status": status}
