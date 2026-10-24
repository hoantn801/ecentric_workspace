# Copyright (c) 2026, eCentric and contributors
"""Tien do luot tao anh host (Studio): ung vien da xong co anh xem truoc."""
import re

from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common, _deps

_CAND = re.compile(r"anchor_c(\d+)\.png$")


class HostImageStatusService:
    def __init__(self, worker=None):
        self.worker = worker or _deps.worker()

    def execute(self, roles, host):
        _common.require_role(roles, C.VIEW_ROLES, C.Msg.NEED_VIEW)
        if not C.HOST_RE.match(str(host or "")):
            raise C.AiLiveError(C.KitMsg.BAD_HOST)
        items = []
        for t in self.worker.call("status", batch_id=C.BATCH_HOST_IMAGE + host).get("tasks") or []:
            done = t.get("state") == "done" and t.get("out")
            m = _CAND.search(t.get("out") or "") if done else None
            items.append({"id": t.get("id"), "state": t.get("state"), "error": str(t.get("error") or "")[:160],
                          "cand": int(m.group(1)) if m else None,
                          "thumb": self.worker.sign(t["out"], width=360) if done else None,
                          "full": self.worker.sign(t["out"]) if done else None})
        fin = ("done", "failed", "cancelled", "blocked")
        return {"host": host, "items": items, "done": bool(items) and all(i["state"] in fin for i in items)}
