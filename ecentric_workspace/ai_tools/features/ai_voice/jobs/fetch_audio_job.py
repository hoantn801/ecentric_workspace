# Copyright (c) 2026, eCentric and contributors
"""Tai MP3 phieu da xong ve ERP (File private) roi xoa phieu tren may eVoice. Loi -> poll thu lai."""
from ecentric_workspace.ai_tools.features.ai_voice.jobs._common import disabled, guarded


def run(name=None):
    if disabled() or not name:
        return None
    from ecentric_workspace.ai_tools.features.ai_voice.application.fetch_audio_service import FetchAudioService
    return guarded("fetch " + str(name), lambda: FetchAudioService().execute(name))
