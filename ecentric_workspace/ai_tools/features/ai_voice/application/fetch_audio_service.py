# Copyright (c) 2026, eCentric and contributors
"""Tai MP3 cua phieu DONE tu eVoice ve File private tren ERP (eVoice chi giu file 24 gio), roi xoa ben may.

QC 15/11: (1) khong giu khoa dong trong luc tai (toi 180 s); (2) xoa file ben may CHI SAU KHI ERP commit
(rollback thi van con ban tren may de tai lai); (3) loi tai -> thu lai gian dan toi 23 gio, khong bo cuoc
sau 8 lan / 16 phut nhu truoc."""
from ecentric_workspace.ai_tools.features.ai_voice import constants as C
from ecentric_workspace.ai_tools.features.ai_voice.application import _deps, _view
from ecentric_workspace.ai_tools.features.ai_voice.domain import rules as R
from ecentric_workspace.ai_tools.features.ai_voice.infrastructure.evoice_client import EVoiceDown, EVoiceHttpError


class FetchAudioService:
    def __init__(self, jobs=None, settings=None, files=None, client=None, now=None, publish=None, after_commit=None):
        self.jobs = jobs or _deps.jobs()
        self.settings = settings or _deps.settings()
        self.files = files or _deps.files()
        self.client = client or _deps.client_factory(self.settings)
        self.now = now or _deps.now
        self.publish = publish or _deps.publish
        self.after_commit = after_commit or _deps.after_commit

    def execute(self, name):
        job = self.jobs.get(name)
        if not _wants_audio(job):
            return "skip"
        attempts = int(job.get("fetch_attempts") or 0) + 1
        try:
            cli = self.client(timeout=180)
            content, ctype = cli.job_audio(job["evoice_job_id"])
        except (EVoiceDown, C.AiVoiceError) as e:
            return self._retry_or_fail(name, attempts, str(e) or C.Msg.DOWN)
        except EVoiceHttpError as e:
            if e.status == 404:                          # may khoi dong lai / qua 24 gio -> khong con file
                return self._fail(name, attempts, C.Msg.LOST)
            return self._retry_or_fail(name, attempts, e.detail)
        if not content:
            return self._retry_or_fail(name, attempts, "File rỗng")
        cur = self.jobs.get(name, for_update=True)
        if not _wants_audio(cur):                         # luong khac da luu / phieu bi xoa trong luc tai
            return "skip"
        ext = "wav" if "wav" in (ctype or "") else "mp3"
        url = self.files.save("giong_doc_%s.%s" % (name, ext), content, C.JOB, name, "audio_file")
        upd = {"audio_file": url, "fetch_attempts": attempts, "last_error": ""}
        if not cur.get("finished_at"):
            upd["finished_at"] = self.now()
        self.jobs.update(name, upd)
        cur.update(upd)
        rid = cur["evoice_job_id"]
        self.after_commit(lambda: _drop_remote(cli, rid))
        self.publish(cur.get("owner"), _view.job(cur))
        return "saved"

    def _retry_or_fail(self, name, attempts, why):
        cur = self.jobs.get(name, for_update=True)
        if not _wants_audio(cur):
            return "skip"
        if R.age_seconds(cur.get("finished_at") or cur.get("submitted_at"), self.now()) >= C.FETCH_GIVE_UP_SECONDS:
            return self._fail(name, attempts, C.Msg.FETCH_GAVE_UP % why)
        self.jobs.update(name, {"fetch_attempts": attempts, "last_error": str(why)[:500], "last_polled_at": self.now()})
        return "retry"

    def _fail(self, name, attempts, msg):
        cur = self.jobs.get(name, for_update=True)
        if not _wants_audio(cur):
            return "skip"
        upd = {"status": C.JobStatus.ERROR, "error": str(msg)[:500], "fetch_attempts": attempts}
        self.jobs.update(name, upd)
        cur.update(upd)
        self.publish(cur.get("owner"), _view.job(cur))
        return "error"


def _wants_audio(job):
    return bool(job) and job["status"] == C.JobStatus.DONE and not job.get("audio_file") and job.get("evoice_job_id")


def _drop_remote(cli, rid):
    try:                                                 # don file ben may (khong bat buoc - may tu xoa sau 24 gio)
        cli.delete_job(rid)
    except Exception:  # noqa: BLE001
        pass
