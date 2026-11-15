# Copyright (c) 2026, eCentric and contributors
"""Huy phieu: chua gui -> huy ngay; dang cho tren may -> may bo khoi hang doi, huy ngay; dang doc -> may dung
o khuc tiep theo va bao lai (callback / poll).

QC 15/11: may mat ket noi -> HUY NGAY tren ERP (truoc day treo "Dang huy..." 3 gio, chiem suat 10 phieu roi
thanh LOI). Neu may van doc xong thi callback ve bi bo qua (phieu da o trang thai cuoi).
Khong giu khoa dong trong luc goi may (toi 15 s)."""
from ecentric_workspace.ai_tools.features.ai_voice import constants as C
from ecentric_workspace.ai_tools.features.ai_voice.application import _deps, _view
from ecentric_workspace.ai_tools.features.ai_voice.domain import rules as R
from ecentric_workspace.ai_tools.features.ai_voice.infrastructure.evoice_client import EVoiceDown, EVoiceHttpError


class CancelJobService:
    def __init__(self, jobs=None, settings=None, client=None, now=None):
        self.jobs = jobs or _deps.jobs()
        self.settings = settings or _deps.settings()
        self.client = client or _deps.client_factory(self.settings)
        self.now = now or _deps.now

    def execute(self, user, roles, name):
        R.require_user(roles)
        job = self.jobs.get(name)
        if not job:
            raise C.AiVoiceError(C.Msg.JOB_NOT_FOUND)
        if not R.can_touch_job(job, user, roles):
            raise C.AiVoicePermission(C.Msg.NOT_YOURS)
        if job["status"] in C.JobStatus.FINAL:
            raise C.AiVoiceError(C.Msg.CANNOT_CANCEL)
        upd = {"cancel_requested": 1}
        if job["status"] == C.JobStatus.PENDING or not job.get("evoice_job_id"):
            upd.update(self._final(C.Msg.CANCELLED))
        else:
            try:
                self.client(timeout=C.POLL_TIMEOUT).delete_job(job["evoice_job_id"])
                if job["status"] == C.JobStatus.QUEUED:
                    upd.update(self._final(C.Msg.CANCELLED))   # may da bo phieu khoi hang doi (khong co callback)
            except EVoiceHttpError as e:
                upd.update(self._final(C.Msg.CANCELLED if e.status == 404 else C.Msg.CANCELLED_OFFLINE))
            except (EVoiceDown, C.AiVoiceError):
                upd.update(self._final(C.Msg.CANCELLED_OFFLINE))
        cur = self.jobs.get(name, for_update=True)
        if not cur:
            raise C.AiVoiceError(C.Msg.JOB_NOT_FOUND)
        if cur["status"] in C.JobStatus.FINAL:            # callback / poll chen vao: giu ket qua that
            return _view.job(cur)
        self.jobs.update(name, upd)
        cur.update(upd)
        return _view.job(cur)

    def _final(self, msg):
        return {"status": C.JobStatus.CANCELLED, "error": msg, "finished_at": self.now(), "position": 0}
