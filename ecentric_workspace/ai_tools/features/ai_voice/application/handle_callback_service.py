# Copyright (c) 2026, eCentric and contributors
"""eVoice bao phieu xong / loi (POST callback). Kiem chu ky HMAC truoc khi tin bat cu gi trong body.

Idempotent: callback lap lai / den tre khong keo phieu da xong lui lai. Xong -> day job nen tai MP3
(khong tai ngay trong callback: eVoice chi cho callback 15 s)."""
import json

from ecentric_workspace.ai_tools.features.ai_voice import constants as C
from ecentric_workspace.ai_tools.features.ai_voice.application import _deps, _view
from ecentric_workspace.ai_tools.features.ai_voice.domain import rules as R


class BadSignature(Exception):
    pass


class HandleCallbackService:
    def __init__(self, jobs=None, settings=None, enqueue=None, now=None, publish=None):
        self.jobs = jobs or _deps.jobs()
        self.settings = settings or _deps.settings()
        self.enqueue = enqueue or _deps.enqueue
        self.now = now or _deps.now
        self.publish = publish or _deps.publish

    def execute(self, raw_body, signature):
        token = self.settings.get(with_token=True).get("token") or ""
        if not R.verify_signature(token, raw_body, signature):
            raise BadSignature()
        try:
            body = json.loads((raw_body or b"").decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return "bad_json"
        if not isinstance(body, dict):
            return "bad_json"
        job = self.jobs.find_by_remote_id(str(body.get("id") or ""), for_update=True)
        if not job:
            return "unknown"
        ref = str(body.get("ref") or "")
        if ref and ref != job["name"]:
            return "ref_mismatch"
        upd = R.remote_update(body)
        if not upd or R.is_stale_update(job["status"], upd["status"]):
            return "stale"
        if upd["status"] in C.JobStatus.FINAL:
            upd["finished_at"] = self.now()
        self.jobs.update(job["name"], upd)
        job.update(upd)
        if upd["status"] == C.JobStatus.DONE and not job.get("audio_file"):
            self.enqueue("fetch_audio_job", name=job["name"])
        self.publish(job.get("owner"), _view.job(job))
        return "ok"
