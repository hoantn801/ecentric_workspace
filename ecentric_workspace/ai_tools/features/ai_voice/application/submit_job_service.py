# Copyright (c) 2026, eCentric and contributors
"""Gui phieu PENDING sang eVoice (POST /v1/jobs). Goi tu job nen ngay sau khi tao + tu poll khi gui lai.

May tat / hang doi day (429) -> giu PENDING, tang so lan thu (poll gui lai theo backoff); qua
SUBMIT_MAX_ATTEMPTS lan -> ERROR. eVoice tu choi noi dung / giong (4xx khac) -> ERROR ngay.

Khong giu khoa dong trong luc goi mang (QC 15/11: khoa + 30 s mang lam nghen huy / callback): doc ->
goi may -> khoa lai, kiem lai trang thai roi moi ghi. Bi huy trong luc gui -> xoa luon phieu ben may."""
from ecentric_workspace.ai_tools.features.ai_voice import constants as C
from ecentric_workspace.ai_tools.features.ai_voice.application import _deps, _view
from ecentric_workspace.ai_tools.features.ai_voice.domain import rules as R
from ecentric_workspace.ai_tools.features.ai_voice.infrastructure.evoice_client import EVoiceDown, EVoiceHttpError


class SubmitJobService:
    def __init__(self, jobs=None, settings=None, client=None, now=None, publish=None):
        self.jobs = jobs or _deps.jobs()
        self.settings = settings or _deps.settings()
        self.client = client or _deps.client_factory(self.settings)
        self.now = now or _deps.now
        self.publish = publish or _deps.publish

    def execute(self, name):
        job = self.jobs.get(name)
        if not job or job["status"] != C.JobStatus.PENDING:
            return "skip"
        if job.get("cancel_requested"):
            return self._write(name, {"status": C.JobStatus.CANCELLED, "error": C.Msg.CANCELLED,
                                      "finished_at": self.now()}) and "cancelled" or "skip"
        attempts = int(job.get("attempts") or 0) + 1
        try:
            cli = self.client()
            remote = cli.create_job(R.job_payload(job, job.get("callback_url") or self._callback_url()))
        except C.AiVoiceError as e:                       # chua cai dat ket noi / dang tat khan
            return self._retry_or_fail(name, attempts, str(e))
        except EVoiceDown as e:
            return self._retry_or_fail(name, attempts, "%s (%s)" % (C.Msg.DOWN, e))
        except EVoiceHttpError as e:
            if e.status == 429:
                return self._retry_or_fail(name, attempts, e.detail)
            if e.status in (401, 403):
                return self._retry_or_fail(name, attempts, "Máy giọng đọc từ chối token: %s" % e.detail)
            self._write(name, {"status": C.JobStatus.ERROR, "error": e.detail[:500], "attempts": attempts,
                               "finished_at": self.now()})
            return "error"
        rid = str((remote or {}).get("id") or "")
        if not rid:
            return self._retry_or_fail(name, attempts, "Máy giọng đọc trả về thiếu mã phiếu")
        cur = self.jobs.get(name, for_update=True)
        if not cur or cur["status"] != C.JobStatus.PENDING or cur.get("cancel_requested"):
            self._drop_remote(cli, rid)                   # da huy / da xoa trong luc gui
            if cur and cur["status"] == C.JobStatus.PENDING:
                self._set(cur, {"status": C.JobStatus.CANCELLED, "error": C.Msg.CANCELLED, "finished_at": self.now()})
                return "cancelled"
            return "raced"
        upd = {"evoice_job_id": rid, "attempts": attempts, "submitted_at": self.now(), "last_error": "",
               "status": C.JobStatus.QUEUED, "position": 0}
        upd.update(R.remote_update(remote))
        if upd["status"] == C.JobStatus.RUNNING:
            upd["started_at"] = self.now()
        self._set(cur, upd)
        return "submitted"

    def _callback_url(self):
        s = self.settings.get()
        base = R.callback_base(s.get("callback_base_url") or self.settings.site_url())
        return base + C.CALLBACK_METHOD if base else ""

    def _retry_or_fail(self, name, attempts, why):
        if attempts >= C.SUBMIT_MAX_ATTEMPTS:
            ok = self._write(name, {"status": C.JobStatus.ERROR, "attempts": attempts, "last_error": why[:500],
                                    "error": (C.Msg.SUBMIT_GAVE_UP % why)[:500], "finished_at": self.now()})
            return "gave_up" if ok else "skip"
        ok = self._write(name, {"attempts": attempts, "last_error": why[:500], "last_polled_at": self.now()})
        return "retry" if ok else "skip"

    def _write(self, name, values):
        """Khoa lai + chi ghi khi phieu van PENDING."""
        cur = self.jobs.get(name, for_update=True)
        if not cur or cur["status"] != C.JobStatus.PENDING:
            return False
        self._set(cur, values)
        return True

    def _set(self, job, values):
        self.jobs.update(job["name"], values)
        job.update(values)
        self.publish(job.get("owner"), _view.job(job))

    @staticmethod
    def _drop_remote(cli, rid):
        try:
            cli.delete_job(rid)
        except Exception:  # noqa: BLE001 - phieu mo coi ben may: callback ve se bi bo qua (khong khop)
            pass
