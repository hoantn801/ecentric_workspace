# Copyright (c) 2026, eCentric and contributors
"""Kho host: moi host tren may chay video (co khung neo), ten hien thi, so clip motion."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common, _deps
from ecentric_workspace.ai_tools.features.ai_live.domain import kit_plan


class ListHostsService:
    def __init__(self, worker=None, labels=None):
        self.worker = worker or _deps.worker()
        self.labels = labels or _deps.labels()

    def execute(self, roles):
        _common.require_role(roles, C.VIEW_ROLES, C.Msg.NEED_VIEW)
        names = self.labels.all()
        hosts = []
        for h in self.worker.call("hosts_list").get("hosts") or []:
            hosts.append({"host": h.get("host"), "label": names.get(h.get("host")) or "", "talks": int(h.get("talks") or 0),
                          "thumb": self.worker.sign(h["anchor"], width=240) if h.get("anchor") else None,
                          "mtime": h.get("mtime")})
        proposal = kit_plan.motion_plan()
        return {"hosts": hosts, "models": [{"id": m[0], "label": m[1], "credits": m[2]} for m in C.IMAGE_MODELS],
                "motion_proposal": proposal, "motion_cost": kit_plan.motion_cost(proposal)}
