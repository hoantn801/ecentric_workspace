# Copyright (c) 2026, eCentric and contributors
"""Chon 1 anh ung vien -> luu thanh khung neo cua host (vao Kho host), dat ten hien thi."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common, _deps


class HostSaveService:
    def __init__(self, worker=None, labels=None):
        self.worker = worker or _deps.worker()
        self.labels = labels or _deps.labels()

    def execute(self, roles, host, cand, label=None):
        _common.require_role(roles, C.VIEW_ROLES, C.Msg.NEED_VIEW)
        host = str(host or "")
        if not C.HOST_RE.match(host):
            raise C.AiLiveError(C.KitMsg.BAD_HOST)
        try:
            cand = int(cand)
        except (TypeError, ValueError):
            raise C.AiLiveError(C.KitMsg.BAD_PICK)
        if not 1 <= cand <= 8:
            raise C.AiLiveError(C.KitMsg.BAD_PICK)
        r = self.worker.call("anchor_pick", host=host, cand=cand)
        if label is not None and str(label).strip():
            self.labels.set(host, str(label).strip()[:80])
        return {"host": host, "anchor": r.get("anchor")}
