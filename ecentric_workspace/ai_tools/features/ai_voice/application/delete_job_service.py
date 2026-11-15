# Copyright (c) 2026, eCentric and contributors
"""Xoa phieu da xong / loi / huy (kem file MP3 tren ERP). Phieu dang chay phai huy truoc."""
from ecentric_workspace.ai_tools.features.ai_voice import constants as C
from ecentric_workspace.ai_tools.features.ai_voice.application import _deps
from ecentric_workspace.ai_tools.features.ai_voice.domain import rules as R


class DeleteJobService:
    def __init__(self, jobs=None, files=None):
        self.jobs = jobs or _deps.jobs()
        self.files = files or _deps.files()

    def execute(self, user, roles, name):
        R.require_user(roles)
        job = self.jobs.get(name, for_update=True)
        if not job:
            raise C.AiVoiceError(C.Msg.JOB_NOT_FOUND)
        if not R.can_touch_job(job, user, roles):
            raise C.AiVoicePermission(C.Msg.NOT_YOURS)
        if job["status"] in C.JobStatus.ACTIVE:
            raise C.AiVoiceError(C.Msg.CANNOT_DELETE)
        self.files.delete(job.get("audio_file"))
        self.jobs.delete(name)
        return {"name": name, "deleted": True}
