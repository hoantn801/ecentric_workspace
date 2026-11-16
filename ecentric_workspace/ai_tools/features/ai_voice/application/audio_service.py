# Copyright (c) 2026, eCentric and contributors
"""Nghe / tai MP3 cua phieu (chu phieu hoac quan ly) va nghe thu giong mau.

Mau giong lay tu may lan dau roi luu File private gan voi ho so giong - lan sau phat tu ERP,
khong goi qua tunnel moi lan bam nghe thu."""
import unicodedata

from ecentric_workspace.ai_tools.features.ai_voice import constants as C
from ecentric_workspace.ai_tools.features.ai_voice.application import _deps
from ecentric_workspace.ai_tools.features.ai_voice.domain import rules as R
from ecentric_workspace.ai_tools.features.ai_voice.infrastructure.evoice_client import EVoiceDown, EVoiceHttpError

_MIME = {"mp3": "audio/mpeg", "wav": "audio/wav", "m4a": "audio/mp4", "flac": "audio/flac", "ogg": "audio/ogg"}


def mime_of(file_name):
    return _MIME.get(str(file_name or "").rsplit(".", 1)[-1].lower(), "application/octet-stream")


class AudioService:
    def __init__(self, jobs=None, profiles=None, settings=None, files=None, client=None):
        self.jobs = jobs or _deps.jobs()
        self.profiles = profiles or _deps.profiles()
        self.settings = settings or _deps.settings()
        self.files = files or _deps.files()
        self.client = client or _deps.client_factory(self.settings)

    def job_audio(self, user, roles, name):
        """-> (ten file tai ve, noi dung bytes, mime)."""
        R.require_user(roles)
        job = self.jobs.get(name)
        if not job:
            raise C.AiVoiceError(C.Msg.JOB_NOT_FOUND)
        if not R.can_touch_job(job, user, roles):
            raise C.AiVoicePermission(C.Msg.NOT_YOURS)
        url = job.get("audio_file")
        content = self.files.content(url) if url else None
        if not content:
            raise C.AiVoiceError(C.Msg.NO_AUDIO)
        ext = str(url).rsplit(".", 1)[-1].lower()
        return "%s.%s" % (_safe_name(job.get("title") or job["name"]), ext), content, mime_of(url)

    def sample(self, user, roles, profile_name):
        R.require_user(roles)
        p = self.profiles.get(profile_name)
        if not p or not p.get("voice_id"):
            raise C.AiVoiceError(C.Msg.VOICE_NOT_FOUND)
        if not (R.is_manager(roles) or R.can_use_profile(p, user, roles)):
            raise C.AiVoicePermission(C.Msg.VOICE_RESTRICTED)
        url = p.get("sample_file")
        content = self.files.content(url) if url else None
        if content:
            return "mau_%s" % url.rsplit("/", 1)[-1], content, mime_of(url)
        try:
            content, ctype = self.client().voice_sample(p["voice_id"])
        except EVoiceDown:
            raise C.AiVoiceError(C.Msg.DOWN)
        except EVoiceHttpError as e:
            raise C.AiVoiceError(e.detail if e.status != 404 else C.Msg.VOICE_NOT_FOUND)
        ext = {"audio/mpeg": "mp3", "audio/wav": "wav", "audio/x-wav": "wav", "audio/flac": "flac",
               "audio/ogg": "ogg", "audio/mp4": "m4a"}.get(ctype, "wav")
        url = self.files.save("mau_giong_%s.%s" % (p["name"], ext), content, C.PROFILE, p["name"], "sample_file")
        self.profiles.update(p["name"], {"sample_file": url})
        return "mau_giong.%s" % ext, content, mime_of(url)


def _safe_name(s):
    """Ten file tai ve: bo dau tieng Viet -> ASCII (header Content-Disposition cua Frappe khong ma hoa UTF-8)."""
    t = unicodedata.normalize("NFKD", str(s).replace("đ", "d").replace("Đ", "D"))
    t = "".join(c for c in t if not unicodedata.combining(c))
    out = "".join(c if (c.isascii() and (c.isalnum() or c in " -_")) else "_" for c in t)[:60].strip()
    return out.replace(" ", "_") or "giong_doc"
