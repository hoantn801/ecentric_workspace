# Copyright (c) 2026, eCentric and contributors
"""Gui phieu giong doc sang may eVoice ngay sau khi tao (enqueue_after_commit). Gui khong duoc -> phieu
giu PENDING, job poll 2 phut gui lai theo backoff."""
from ecentric_workspace.ai_tools.features.ai_voice.jobs._common import disabled, guarded


def run(name=None):
    if disabled() or not name:
        return None
    from ecentric_workspace.ai_tools.features.ai_voice.application.submit_job_service import SubmitJobService
    return guarded("submit " + str(name), lambda: SubmitJobService().execute(name))
