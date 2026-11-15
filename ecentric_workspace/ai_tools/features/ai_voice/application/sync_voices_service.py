# Copyright (c) 2026, eCentric and contributors
"""Doi chieu thu vien giong ERP voi may eVoice.

- sync (quan ly bam "Dong bo tu may"): giong co tren may ma ERP chua co -> tao ho so nguon "may",
  trang thai NGUNG cho toi khi quan ly nhap bang chung dong y va bat; giong ERP khong con tren may -> danh dau.
- reconcile (job nen): ho so PROCESSING bi Cloudflare cat ngang -> tim giong co dau [erp:<ho so>] tren may de gan ma;
  qua 30 phut khong thay -> FAILED."""
from ecentric_workspace.ai_tools.features.ai_voice import constants as C
from ecentric_workspace.ai_tools.features.ai_voice.application import _deps, _view
from ecentric_workspace.ai_tools.features.ai_voice.domain import rules as R
from ecentric_workspace.ai_tools.features.ai_voice.infrastructure.evoice_client import EVoiceDown, EVoiceHttpError

RECONCILE_AFTER = 120
RECONCILE_GIVE_UP = 30 * 60


class SyncVoicesService:
    def __init__(self, profiles=None, settings=None, client=None, now=None):
        self.profiles = profiles or _deps.profiles()
        self.settings = settings or _deps.settings()
        self.client = client or _deps.client_factory(self.settings)
        self.now = now or _deps.now

    def execute(self, roles):
        R.require_manager(roles)
        remote = self._remote()
        now = self.now()
        everyone = self.profiles.list(include_inactive=True)
        local = {p["voice_id"]: p for p in everyone if p.get("voice_id")}
        by_name = {p["name"]: p for p in everyone}
        added = updated = missing = 0
        seen = set()
        for v in remote:
            vid = str(v.get("id") or "")
            if not vid or vid in seen:
                continue
            seen.add(vid)
            p = local.get(vid)
            gender = v.get("gender") if v.get("gender") in C.GENDERS else ""
            owner = by_name.get(R.marker_of(v.get("description")) or "")
            if p is None and owner is not None and not owner.get("voice_id"):
                # giong ERP vua tao (upload bi cat ngang) -> gan ma vao dung ho so, KHONG tao ho so "tu may" trung
                upd = {"voice_id": vid, "last_synced": now, "missing_on_server": 0, "upload_error": ""}
                if owner.get("status") in (C.VoiceStatus.PROCESSING, C.VoiceStatus.FAILED):
                    upd["status"] = C.VoiceStatus.ACTIVE
                self.profiles.update(owner["name"], upd)
                owner.update(upd)
                local[vid] = owner
                updated += 1
                continue
            if p is None:
                self.profiles.insert({"voice_id": vid, "voice_name": (str(v.get("name") or vid))[:C.MAX_NAME],
                                      "gender": gender, "description": R.strip_marker(v.get("description"))[:C.MAX_DESC],
                                      "status": C.VoiceStatus.DISABLED, "source": C.VoiceSource.MACHINE,
                                      "last_synced": now, "missing_on_server": 0})
                added += 1
                continue
            upd = {"last_synced": now, "missing_on_server": 0}
            if p.get("source") == C.VoiceSource.MACHINE:
                upd.update({"voice_name": (str(v.get("name") or vid))[:C.MAX_NAME], "gender": gender,
                            "description": R.strip_marker(v.get("description"))[:C.MAX_DESC]})
            self.profiles.update(p["name"], upd)
            updated += 1
        for vid, p in local.items():
            if vid not in seen and not p.get("missing_on_server"):
                self.profiles.update(p["name"], {"missing_on_server": 1})
                missing += 1
        return {"added": added, "updated": updated, "missing": missing,
                "voices": [_view.profile(p, manager=True) for p in self.profiles.list(include_inactive=True)]}

    def reconcile(self):
        """Job nen. Tra ve so ho so da xu ly."""
        pending = [p for p in self.profiles.list(include_inactive=True) if p.get("status") == C.VoiceStatus.PROCESSING]
        now = self.now()
        due = [p for p in pending if R.age_seconds(p.get("upload_started_at") or p.get("modified"), now) >= RECONCILE_AFTER]
        if not due:
            return 0
        try:
            remote = self._remote()
        except C.AiVoiceError:
            remote = None
        known = self.profiles.known_voice_ids()
        n = 0
        for p in due:
            vid = R.match_remote_voice(remote, p["name"], known) if remote is not None else None
            if vid:
                known.add(vid)
                self.profiles.update(p["name"], {"voice_id": vid, "status": C.VoiceStatus.ACTIVE, "upload_error": "",
                                                 "last_synced": now, "missing_on_server": 0})
                n += 1
            elif R.age_seconds(p.get("upload_started_at") or p.get("modified"), now) >= RECONCILE_GIVE_UP:
                self.profiles.update(p["name"], {"status": C.VoiceStatus.FAILED,
                                                 "upload_error": "Không xác nhận được giọng trên máy sau 30 phút - bấm Thử lại."})
                n += 1
        return n

    def _remote(self):
        try:
            return self.client().voices()
        except EVoiceDown:
            raise C.AiVoiceError(C.Msg.DOWN)
        except EVoiceHttpError as e:
            raise C.AiVoiceError(e.detail)
