# Copyright (c) 2026, eCentric and contributors
"""Gui file giong mau sang may eVoice de tao giong (queue long: may cat mau + khu on + chep loi vai phut)."""
from ecentric_workspace.ai_tools.features.ai_voice.jobs._common import disabled, guarded


def run(name=None):
    if disabled() or not name:
        return None
    from ecentric_workspace.ai_tools.features.ai_voice.application.upload_voice_service import UploadVoiceService
    return guarded("upload voice " + str(name), lambda: UploadVoiceService().execute(name))
