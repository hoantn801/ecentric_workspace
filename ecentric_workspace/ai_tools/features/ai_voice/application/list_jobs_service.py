# Copyright (c) 2026, eCentric and contributors
"""Danh sach phieu: cua minh (mac dinh) hoac tat ca (chi quan ly). Lay 1 phieu kem noi dung (de Tao lai)."""
from ecentric_workspace.ai_tools.features.ai_voice import constants as C
from ecentric_workspace.ai_tools.features.ai_voice.application import _deps, _view
from ecentric_workspace.ai_tools.features.ai_voice.domain import rules as R


class ListJobsService:
    def __init__(self, jobs=None):
        self.jobs = jobs or _deps.jobs()

    def execute(self, user, roles, scope="mine", status=None, start=0, limit=C.LIST_LIMIT):
        R.require_user(roles)
        owner = None if (scope == "all" and R.is_manager(roles)) else user
        statuses = None
        if status == "active":
            statuses = C.JobStatus.ACTIVE
        elif status in C.JobStatus.ALL:
            statuses = (status,)
        try:
            start, limit = max(int(start or 0), 0), min(max(int(limit or C.LIST_LIMIT), 1), 200)
        except (TypeError, ValueError):
            start, limit = 0, C.LIST_LIMIT
        rows = self.jobs.list(owner=owner, statuses=statuses, limit=limit + 1, start=start)
        return {"jobs": [_view.job(r) for r in rows[:limit]], "more": len(rows) > limit,
                "scope": "all" if owner is None else "mine"}

    def get(self, user, roles, name):
        R.require_user(roles)
        job = self.jobs.get(name)
        if not job:
            raise C.AiVoiceError(C.Msg.JOB_NOT_FOUND)
        if not R.can_touch_job(job, user, roles):
            raise C.AiVoicePermission(C.Msg.NOT_YOURS)
        d = _view.job(job, with_text=True)
        d["voice_profile"] = job.get("voice_profile")
        d["breath"] = job.get("breath")
        return d
