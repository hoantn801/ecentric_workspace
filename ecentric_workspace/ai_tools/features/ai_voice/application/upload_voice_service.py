# Copyright (c) 2026, eCentric and contributors
"""Job nen: gui file mau sang eVoice (POST /v1/voices) cho ho so PROCESSING.

Cloudflare cat yeu cau qua 100 s (524) trong khi may co the van xu ly tiep va luu giong -> KHONG bao loi ngay:
giu PROCESSING, reconcile (poll) tim giong co DAU [erp:<ho so>] trong mo ta de gan ma. Loi that (file hong,
may tu choi) -> FAILED kem ly do, quan ly bam Thu lai.
Khong giu khoa dong trong luc gui (toi 10 phut): doc -> gui -> khoa lai, kiem van PROCESSING roi moi ghi."""
import base64

from ecentric_workspace.ai_tools.features.ai_voice import constants as C
from ecentric_workspace.ai_tools.features.ai_voice.application import _deps
from ecentric_workspace.ai_tools.features.ai_voice.domain import rules as R
from ecentric_workspace.ai_tools.features.ai_voice.infrastructure.evoice_client import EVoiceDown, EVoiceHttpError


class UploadVoiceService:
    def __init__(self, profiles=None, settings=None, files=None, client=None, now=None):
        self.profiles = profiles or _deps.profiles()
        self.settings = settings or _deps.settings()
        self.files = files or _deps.files()
        self.client = client or _deps.client_factory(self.settings)
        self.now = now or _deps.now

    def execute(self, name):
        p = self.profiles.get(name)
        if not p or p.get("status") != C.VoiceStatus.PROCESSING:
            return "skip"
        info = self.files.info(p.get("upload_file"))
        content = self.files.content(p.get("upload_file")) if info else None
        if not content:
            return self._fail(name, C.Msg.FILE_REQUIRED)
        payload = {"name": p["voice_name"], "gender": p.get("gender") or "",
                   "description": R.with_marker(p.get("description"), name),
                   "filename": info["file_name"] or "voice.wav",
                   "audio_base64": base64.b64encode(content).decode("ascii"),
                   "consent": {"by": p.get("consent_by") or "", "at": str(p.get("consent_date") or ""),
                               "note": (p.get("consent_note") or "")[:300]}}
        try:
            res = self.client(timeout=C.UPLOAD_TIMEOUT).create_voice(payload, timeout=C.UPLOAD_TIMEOUT)
        except C.AiVoiceError as e:
            return self._fail(name, str(e))
        except EVoiceDown as e:
            if e.timeout:                                 # may co the van dang xu ly -> poll doi chieu theo dau [erp:]
                return "pending_check" if self._write(name, {"upload_error": "Máy đang xử lý lâu - ERP sẽ tự kiểm tra lại."}) else "skip"
            return self._fail(name, "%s (%s)" % (C.Msg.DOWN, e))
        except EVoiceHttpError as e:
            return self._fail(name, e.detail)
        vid = str((res or {}).get("id") or "")
        if not vid:
            return self._fail(name, "Máy giọng đọc trả về thiếu mã giọng")
        ok = self._write(name, {"voice_id": vid, "status": C.VoiceStatus.ACTIVE, "upload_error": "",
                                "ref_text": str(res.get("ref_text") or "")[:2000],
                                "clip_seconds": res.get("clip_seconds") or 0, "last_synced": self.now(),
                                "missing_on_server": 0})
        return "active" if ok else "skip"

    def _fail(self, name, why):
        return "failed" if self._write(name, {"status": C.VoiceStatus.FAILED, "upload_error": str(why)[:500]}) else "skip"

    def _write(self, name, values):
        if self.profiles.lock(name) != C.VoiceStatus.PROCESSING:   # bi xoa / da gan ma trong luc gui
            return False
        self.profiles.update(name, values)
        return True
