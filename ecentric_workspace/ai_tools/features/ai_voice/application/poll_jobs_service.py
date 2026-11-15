# Copyright (c) 2026, eCentric and contributors
"""Job nen moi 2 phut - luoi an toan khi callback khong toi (ERP tat / mang chap chon):
- PENDING: gui lai theo backoff (SubmitJobService); phieu vua tao (< 90 s, chua thu lan nao) de job gui ngay lo.
- QUEUED / RUNNING: callback chua toi sau POLL_GRACE_SECONDS -> hoi trang thai; 404 = may mat phieu;
  doc qua RUNNING_TIMEOUT_SECONDS (tinh tu luc BAT DAU doc) / nam hang doi qua QUEUED_TIMEOUT_SECONDS -> ERROR.
- DONE chua co file: tai lai, gian dan (FetchAudioService).
Ngat mach: gap may mat ket noi mot lan -> cac phieu con lai trong luot nay bo qua (khong cho timeout tung phieu).
Khong giu khoa dong trong luc goi mang: doc -> hoi may -> khoa lai, kiem trang thai chua doi roi moi ghi."""
from ecentric_workspace.ai_tools.features.ai_voice import constants as C
from ecentric_workspace.ai_tools.features.ai_voice.application import _deps, _view
from ecentric_workspace.ai_tools.features.ai_voice.application.fetch_audio_service import FetchAudioService
from ecentric_workspace.ai_tools.features.ai_voice.application.submit_job_service import SubmitJobService
from ecentric_workspace.ai_tools.features.ai_voice.domain import rules as R
from ecentric_workspace.ai_tools.features.ai_voice.infrastructure.evoice_client import EVoiceDown, EVoiceHttpError

FRESH_PENDING_SECONDS = 90


class PollJobsService:
    def __init__(self, jobs=None, settings=None, client=None, now=None, publish=None, submit=None, fetch=None):
        self.jobs = jobs or _deps.jobs()
        self.settings = settings or _deps.settings()
        self.client = client or _deps.client_factory(self.settings)
        self.now = now or _deps.now
        self.publish = publish or _deps.publish
        self.submit = submit or SubmitJobService(jobs=self.jobs, settings=self.settings, client=self.client,
                                                 now=self.now, publish=self.publish)
        self.fetch = fetch or FetchAudioService(jobs=self.jobs, settings=self.settings, client=self.client,
                                                now=self.now, publish=self.publish)
        self.down = False

    def targets(self):
        return self.jobs.active_names()

    def process(self, name):
        job = self.jobs.get(name)
        if not job:
            return "gone"
        now = self.now()
        st = job["status"]
        if st == C.JobStatus.DONE:
            if job.get("audio_file"):
                return "skip"
            if R.age_seconds(job.get("last_polled_at"), now) < R.fetch_backoff_seconds(job.get("fetch_attempts")):
                return "wait"
            return self._net(lambda: self.fetch.execute(name))
        if st == C.JobStatus.PENDING:
            if job.get("cancel_requested"):
                return self._finish(name, st, C.JobStatus.CANCELLED, C.Msg.CANCELLED)
            if not job.get("attempts") and R.age_seconds(job.get("creation"), now) < FRESH_PENDING_SECONDS:
                return "wait"
            wait = R.submit_backoff_seconds(job.get("attempts"))
            if R.age_seconds(job.get("last_polled_at") or job.get("modified"), now) < wait:
                return "wait"
            return self._net(lambda: self.submit.execute(name))
        if st not in (C.JobStatus.QUEUED, C.JobStatus.RUNNING):
            return "skip"
        if self._timed_out(job, now):
            self._try_delete(job)
            return self._finish(name, st, C.JobStatus.ERROR, C.Msg.TIMEOUT)
        if job.get("cancel_requested"):
            self._try_delete(job)
        elif R.age_seconds(job.get("modified"), now) < C.POLL_GRACE_SECONDS:
            return "wait"
        if self.down:
            return "down"
        try:
            remote = self.client(timeout=C.POLL_TIMEOUT).get_job(job["evoice_job_id"])
        except EVoiceHttpError as e:
            if e.status == 404:
                final = C.JobStatus.CANCELLED if job.get("cancel_requested") else C.JobStatus.ERROR
                return self._finish(name, st, final, C.Msg.CANCELLED if job.get("cancel_requested") else C.Msg.LOST)
            self._touch(name, st, {"last_error": e.detail[:500], "last_polled_at": now})
            return "http_error"
        except (EVoiceDown, C.AiVoiceError) as e:
            self.down = True
            self._touch(name, st, {"last_error": str(e)[:500], "last_polled_at": now})
            return "down"
        upd = R.remote_update(remote)
        cur = self.jobs.get(name, for_update=True)
        if not cur or cur["status"] != st:
            return "changed"                              # callback / huy chen vao trong luc hoi may
        if not upd or R.is_stale_update(st, upd["status"]):
            self.jobs.update(name, {"last_polled_at": now})
            return "same"
        upd["last_polled_at"] = now
        if upd["status"] == C.JobStatus.RUNNING and not cur.get("started_at"):
            upd["started_at"] = now
        if upd["status"] in C.JobStatus.FINAL:
            upd["finished_at"] = now
        self.jobs.update(name, upd)
        cur.update(upd)
        self.publish(cur.get("owner"), _view.job(cur))
        if upd["status"] == C.JobStatus.DONE:
            return self._net(lambda: self.fetch.execute(name))
        return upd["status"]

    def _net(self, fn):
        return "down" if self.down else fn()

    def _timed_out(self, job, now):
        if job["status"] == C.JobStatus.RUNNING:
            return R.age_seconds(job.get("started_at") or job.get("submitted_at"), now) > C.RUNNING_TIMEOUT_SECONDS
        return R.age_seconds(job.get("submitted_at"), now) > C.QUEUED_TIMEOUT_SECONDS

    def _try_delete(self, job):
        if self.down:
            return
        try:
            self.client(timeout=C.POLL_TIMEOUT).delete_job(job["evoice_job_id"])
        except EVoiceDown:
            self.down = True
        except Exception:  # noqa: BLE001 - lan poll sau thu lai
            pass

    def _touch(self, name, st, values):
        cur = self.jobs.get(name, for_update=True)
        if cur and cur["status"] == st:
            self.jobs.update(name, values)

    def _finish(self, name, expect, status, msg):
        cur = self.jobs.get(name, for_update=True)
        if not cur or cur["status"] != expect:
            return "changed"
        upd = {"status": status, "error": msg, "finished_at": self.now(), "position": 0}
        self.jobs.update(name, upd)
        cur.update(upd)
        self.publish(cur.get("owner"), _view.job(cur))
        return status
