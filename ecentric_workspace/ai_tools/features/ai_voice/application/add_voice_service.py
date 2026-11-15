# Copyright (c) 2026, eCentric and contributors
"""Them giong tu ERP (quan ly): file mau + bang chung dong y bat buoc. Luu ho so PROCESSING roi day job nen
gui file sang may (cat ~10 s, khu on, chep loi - co the vai phut). Giong loi thi "Thu lai" o day."""
from ecentric_workspace.ai_tools.features.ai_voice import constants as C
from ecentric_workspace.ai_tools.features.ai_voice.application import _deps, _view
from ecentric_workspace.ai_tools.features.ai_voice.domain import rules as R


class AddVoiceService:
    def __init__(self, profiles=None, files=None, enqueue=None, now=None):
        self.profiles = profiles or _deps.profiles()
        self.files = files or _deps.files()
        self.enqueue = enqueue or _deps.enqueue
        self.now = now or _deps.now

    def execute(self, user, roles, payload):
        R.require_manager(roles)
        payload = payload or {}
        name, gender, desc = R.validate_voice_fields(payload.get("voice_name"), payload.get("gender"),
                                                     payload.get("description"))
        consent_by, consent_date = R.validate_consent(payload.get("consent_by"), payload.get("consent_date"),
                                                      payload.get("consent_confirmed"))
        sample_url = str(payload.get("sample_url") or "").strip()
        if not sample_url:
            raise C.AiVoiceError(C.Msg.FILE_REQUIRED)
        info = self.files.info(sample_url)
        if not info:
            raise C.AiVoiceError(C.Msg.FILE_REQUIRED)
        if info["owner"] != user and not R.is_admin(roles):
            raise C.AiVoicePermission(C.Msg.FILE_NOT_YOURS)
        R.validate_sample_file(info["file_name"] or sample_url, info["size"])
        consent_file = str(payload.get("consent_file") or "").strip()
        if consent_file:
            ci = self.files.info(consent_file)
            if not ci or (ci["owner"] != user and not R.is_admin(roles)):
                raise C.AiVoicePermission(C.Msg.FILE_NOT_YOURS)
        values = {
            "voice_name": name, "gender": gender, "description": desc,
            "brand": str(payload.get("brand") or "").strip()[:80],
            "owner_user": str(payload.get("owner_user") or "").strip() or None,
            "restricted": 1 if str(payload.get("restricted") or "0") in ("1", "true", "True") else 0,
            "status": C.VoiceStatus.PROCESSING, "source": C.VoiceSource.ERP,
            "consent_by": consent_by, "consent_date": consent_date,
            "consent_note": str(payload.get("consent_note") or "").strip()[:1000],
            "consent_file": consent_file or None,
            "upload_file": sample_url, "upload_started_at": self.now(), "upload_error": "",
        }
        pname = self.profiles.insert(values)
        self.enqueue("upload_voice_job", queue="long", timeout=C.UPLOAD_TIMEOUT + 120, name=pname)
        return _view.profile(self.profiles.get(pname), manager=True)

    def retry(self, user, roles, name):
        R.require_manager(roles)
        p = self.profiles.get(name)
        if not p:
            raise C.AiVoiceError(C.Msg.PROFILE_NOT_FOUND)
        if p.get("status") != C.VoiceStatus.FAILED or p.get("source") != C.VoiceSource.ERP:
            raise C.AiVoiceError(C.Msg.PROFILE_BUSY)
        self.profiles.update(name, {"status": C.VoiceStatus.PROCESSING, "upload_error": "",
                                    "upload_started_at": self.now()})
        self.enqueue("upload_voice_job", queue="long", timeout=C.UPLOAD_TIMEOUT + 120, name=name)
        return _view.profile(self.profiles.get(name), manager=True)
