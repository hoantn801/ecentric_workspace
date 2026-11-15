# Copyright (c) 2026, eCentric and contributors
"""Tao phieu giong doc: kiem noi dung + giong + tham so, luu PENDING, day job nen gui sang may.

Giong brand ("brand:<ten>"): hoi may brand dang dung giong nao NGAY LUC TAO, doi chieu voi thu vien ERP
(dong y + han che + dang dung) roi khoa vao dung ma giong do (QC 15/11: truoc day brand: bo qua moi luat).
Dia chi callback tinh luc tao (dang trong request -> dung ten mien that, khong phai trong job nen)."""
from ecentric_workspace.ai_tools.features.ai_voice import constants as C
from ecentric_workspace.ai_tools.features.ai_voice.application import _deps, _view
from ecentric_workspace.ai_tools.features.ai_voice.domain import rules as R
from ecentric_workspace.ai_tools.features.ai_voice.infrastructure.evoice_client import EVoiceDown, EVoiceHttpError


class CreateJobService:
    def __init__(self, jobs=None, profiles=None, enqueue=None, settings=None, client=None):
        self.jobs = jobs or _deps.jobs()
        self.profiles = profiles or _deps.profiles()
        self.enqueue = enqueue or _deps.enqueue
        self.settings = settings or _deps.settings()
        self.client = client or _deps.client_factory(self.settings)

    def execute(self, user, roles, payload):
        R.require_user(roles)
        payload = payload or {}
        text = R.validate_text(payload.get("text"))
        voice_key, voice_label, profile_name = self._voice(user, roles, payload.get("voice"))
        values = {
            "title": R.norm_title(payload.get("title"), text),
            "text": text,
            "chars": len(text),
            "voice_key": voice_key,
            "voice_label": voice_label,
            "voice_profile": profile_name,
            "quality": R.norm_quality(payload.get("quality")),
            "speed": R.norm_speed(payload.get("speed")),
            "language": R.norm_language(payload.get("language")),
            "breath": 0 if str(payload.get("breath", 1)).strip().lower() in ("0", "false", "off") else 1,
            "status": C.JobStatus.PENDING,
            "callback_url": self._callback_url(),
        }
        active = self.jobs.count_active(user)
        if active >= C.MAX_ACTIVE_PER_USER:
            raise C.AiVoiceError(C.Msg.TOO_MANY % (active, C.MAX_ACTIVE_PER_USER))
        name = self.jobs.insert(values)
        self.enqueue("submit_job_job", name=name)
        return _view.job(self.jobs.get(name))

    def _voice(self, user, roles, voice):
        """'profile:<ten ban ghi>' (thu vien ERP) hoac 'brand:<ten brand>' (giong dang dung cua brand tren may)."""
        v = str(voice or "").strip()
        if v.startswith("brand:"):
            brand = v[6:].strip()
            if not brand or len(brand) > 80:
                raise C.AiVoiceError(C.Msg.BAD_VOICE)
            p = self._brand_profile(brand)
            if not R.can_use_profile(p, user, roles):
                raise C.AiVoicePermission(C.Msg.VOICE_RESTRICTED)
            return p["voice_id"], ("Brand %s · %s" % (brand, p.get("voice_name") or p["voice_id"]))[:140], p["name"]
        if v.startswith("profile:"):
            p = self.profiles.get(v[8:].strip())
            if not p or p.get("status") == C.VoiceStatus.DISABLED and not R.is_manager(roles):
                raise C.AiVoiceError(C.Msg.VOICE_NOT_FOUND)
            if p.get("status") != C.VoiceStatus.ACTIVE or not p.get("voice_id"):
                raise C.AiVoiceError(C.Msg.VOICE_NOT_READY)
            if not R.can_use_profile(p, user, roles):
                raise C.AiVoicePermission(C.Msg.VOICE_RESTRICTED)
            return p["voice_id"], p.get("voice_name") or p["voice_id"], p["name"]
        raise C.AiVoiceError(C.Msg.BAD_VOICE)

    def _brand_profile(self, brand):
        try:
            rows = self.client(timeout=10).brands()
        except (EVoiceDown, EVoiceHttpError):
            raise C.AiVoiceError(C.Msg.BRAND_NEEDS_MACHINE)
        b = next((x for x in rows if str(x.get("name") or "") == brand), None)
        if not b:
            raise C.AiVoiceError(C.Msg.VOICE_NOT_FOUND)
        if not b.get("current"):
            raise C.AiVoiceError(C.Msg.BRAND_NO_VOICE)
        p = self.profiles.get_by_voice_id(str(b["current"]))
        if not p or p.get("status") != C.VoiceStatus.ACTIVE or not (p.get("consent_by") and p.get("consent_date")):
            raise C.AiVoiceError(C.Msg.BRAND_VOICE_UNKNOWN)
        return p

    def _callback_url(self):
        s = self.settings.get()
        base = R.callback_base(s.get("callback_base_url") or self.settings.site_url())
        return base + C.CALLBACK_METHOD if base else ""
