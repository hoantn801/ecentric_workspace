# Copyright (c) 2026, eCentric and contributors
"""Sua ho so giong tren ERP (quan ly): ten hien thi, mo ta, brand, chu giong, han che, bang chung dong y,
bat / ngung. BAT giong bat buoc da co bang chung dong y (ten nguoi cho giong + ngay).
Ten / mo ta chi doi tren ERP (eVoice chua co lenh sua giong)."""
from ecentric_workspace.ai_tools.features.ai_voice import constants as C
from ecentric_workspace.ai_tools.features.ai_voice.application import _deps, _view
from ecentric_workspace.ai_tools.features.ai_voice.domain import rules as R


class UpdateVoiceService:
    def __init__(self, profiles=None, files=None):
        self.profiles = profiles or _deps.profiles()
        self.files = files or _deps.files()

    def execute(self, user, roles, name, payload):
        R.require_manager(roles)
        p = self.profiles.get(name)
        if not p:
            raise C.AiVoiceError(C.Msg.PROFILE_NOT_FOUND)
        payload = payload or {}
        upd = {}
        if "voice_name" in payload or "gender" in payload or "description" in payload:
            vn, g, d = R.validate_voice_fields(payload.get("voice_name", p.get("voice_name")),
                                               payload.get("gender", p.get("gender")),
                                               payload.get("description", p.get("description")))
            upd.update({"voice_name": vn, "gender": g, "description": d})
        if "brand" in payload:
            upd["brand"] = str(payload.get("brand") or "").strip()[:80]
        if "owner_user" in payload:
            upd["owner_user"] = str(payload.get("owner_user") or "").strip() or None
        if "restricted" in payload:
            upd["restricted"] = 1 if str(payload.get("restricted")) in ("1", "true", "True") else 0
        if "consent_by" in payload or "consent_date" in payload or "consent_confirmed" in payload:
            by, date = R.validate_consent(payload.get("consent_by"), payload.get("consent_date"),
                                          payload.get("consent_confirmed"))
            upd.update({"consent_by": by, "consent_date": date,
                        "consent_note": str(payload.get("consent_note") or "").strip()[:1000]})
            cf = str(payload.get("consent_file") or "").strip()
            if cf and cf != p.get("consent_file"):
                ci = self.files.info(cf)
                if not ci or (ci["owner"] != user and not R.is_admin(roles)):
                    raise C.AiVoicePermission(C.Msg.FILE_NOT_YOURS)
                upd["consent_file"] = cf
        if "status" in payload:
            st = str(payload.get("status") or "")
            if st not in (C.VoiceStatus.ACTIVE, C.VoiceStatus.DISABLED):
                raise C.AiVoiceError(C.Msg.PROFILE_BUSY)
            if p.get("status") in (C.VoiceStatus.PROCESSING, C.VoiceStatus.FAILED):
                raise C.AiVoiceError(C.Msg.PROFILE_BUSY)
            if st == C.VoiceStatus.ACTIVE:
                merged = dict(p, **upd)
                if not (merged.get("consent_by") and merged.get("consent_date")):
                    raise C.AiVoiceError(C.Msg.CONSENT_REQUIRED)
                if not merged.get("voice_id"):
                    raise C.AiVoiceError(C.Msg.VOICE_NOT_READY)
            upd["status"] = st
        if upd:
            self.profiles.update(name, upd)
        return _view.profile(self.profiles.get(name), manager=True)
