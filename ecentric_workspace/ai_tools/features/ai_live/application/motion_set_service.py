# Copyright (c) 2026, eCentric and contributors
"""Gen bo motion cho host (clip noi cam, nhieu do dai). dry_run=1: chi tra ke hoach + uoc tinh chi phi."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common, _deps
from ecentric_workspace.ai_tools.features.ai_live.domain import kit_plan

_HOST = __import__("re").compile(r"^[A-Za-z0-9_.-]{1,96}$")


class MotionSetService:
    def __init__(self, worker=None):
        self.worker = worker or _deps.worker()

    def execute(self, roles, host, plan=None, dry_run=True):
        _common.require_role(roles, C.VIEW_ROLES, C.Msg.NEED_VIEW)
        host = str(host or "")
        if not _HOST.match(host):
            raise C.AiLiveError(C.KitMsg.BAD_HOST)
        plan = kit_plan.motion_plan(_common.parse_json(plan, "bộ motion") if isinstance(plan, str) else plan)
        cost = kit_plan.motion_cost(plan)
        if dry_run:
            return {"host": host, "plan": plan, "cost": cost, "queued": 0}
        known = [h.get("host") for h in self.worker.call("hosts_list").get("hosts") or []]
        if host not in known:
            raise C.AiLiveError("Host chưa có khung neo trên máy chạy video - lưu ảnh host vào kho trước.")
        ids = self.worker.call("enqueue", batch_id=C.BATCH_MOTION + host, steps=[{"op": "motion_set", "host": host, "plan": plan}]).get("task_ids") or []
        return {"host": host, "plan": plan, "cost": cost, "queued": len(ids)}
