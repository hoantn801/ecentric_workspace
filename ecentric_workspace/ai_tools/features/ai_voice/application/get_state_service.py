# Copyright (c) 2026, eCentric and contributors
"""Du lieu mo trang /ai-voice: quyen, lua chon (chat luong, ngon ngu), giong duoc dung, phieu gan day.
Khong goi may eVoice (trang mo nhanh ca khi may tat) - trang thai may lay rieng qua MachineStatusService."""
from ecentric_workspace.ai_tools.features.ai_voice import constants as C
from ecentric_workspace.ai_tools.features.ai_voice.application import _deps, _view
from ecentric_workspace.ai_tools.features.ai_voice.domain import rules as R


class GetStateService:
    def __init__(self, jobs=None, profiles=None, settings=None):
        self.jobs = jobs or _deps.jobs()
        self.profiles = profiles or _deps.profiles()
        self.settings = settings or _deps.settings()

    def execute(self, user, roles):
        R.require_user(roles)
        manager, admin = R.is_manager(roles), R.is_admin(roles)
        s = self.settings.get()
        voices = [_view.profile(p, manager=manager) for p in self.profiles.list(include_inactive=manager)
                  if manager or R.can_use_profile(p, user, roles)]
        recent = self.jobs.list(owner=user, limit=20)
        return {
            "user": user, "is_manager": manager, "is_admin": admin,
            "configured": bool(s.get("token_set") and s.get("base_url")),
            "defaults": {"quality": s.get("default_quality") or C.DEFAULT_QUALITY,
                         "speed": float(s.get("default_speed") or C.SPEED_DEFAULT), "language": "vi"},
            "qualities": [{"value": k, "label": lb, "hint": h} for k, lb, h in C.QUALITIES],
            "languages": [{"value": k, "label": lb} for k, lb in C.LANGUAGES],
            "genders": list(C.GENDERS),
            "limits": {"max_chars": C.MAX_CHARS, "speed_min": C.SPEED_MIN, "speed_max": C.SPEED_MAX,
                       "max_active": C.MAX_ACTIVE_PER_USER, "max_voice_mb": C.MAX_VOICE_BYTES // (1024 * 1024),
                       "voice_exts": list(C.VOICE_EXTS)},
            "voices": voices,
            "jobs": [_view.job(j) for j in recent],
        }
