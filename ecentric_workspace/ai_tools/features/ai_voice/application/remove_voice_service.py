# Copyright (c) 2026, eCentric and contributors
"""Xoa ho so giong khoi ERP (quan ly). Tuy chon xoa luon tren may eVoice (eC Live dang dung giong do se mat!).
Phieu cu giu nguyen (ten giong luu san tren phieu)."""
from ecentric_workspace.ai_tools.features.ai_voice import constants as C
from ecentric_workspace.ai_tools.features.ai_voice.application import _deps
from ecentric_workspace.ai_tools.features.ai_voice.domain import rules as R
from ecentric_workspace.ai_tools.features.ai_voice.infrastructure.evoice_client import EVoiceDown, EVoiceHttpError


class RemoveVoiceService:
    def __init__(self, profiles=None, settings=None, client=None):
        self.profiles = profiles or _deps.profiles()
        self.settings = settings or _deps.settings()
        self.client = client or _deps.client_factory(self.settings)

    def execute(self, roles, name, from_machine=False):
        R.require_manager(roles)
        p = self.profiles.get(name)
        if not p:
            raise C.AiVoiceError(C.Msg.PROFILE_NOT_FOUND)
        if p.get("status") == C.VoiceStatus.PROCESSING:
            raise C.AiVoiceError(C.Msg.PROFILE_BUSY)
        if from_machine and p.get("voice_id"):
            try:
                self.client().delete_voice(p["voice_id"])
            except EVoiceDown:
                raise C.AiVoiceError(C.Msg.DOWN)
            except EVoiceHttpError as e:
                if e.status != 404:
                    raise C.AiVoiceError(e.detail)
        self.profiles.delete(name)
        return {"name": name, "deleted": True, "from_machine": bool(from_machine and p.get("voice_id"))}
