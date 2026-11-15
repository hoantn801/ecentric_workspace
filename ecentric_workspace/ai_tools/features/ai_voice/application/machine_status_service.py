# Copyright (c) 2026, eCentric and contributors
"""Trang thai may giong doc (/health) + danh sach brand (giong dang dung) - nho 30 / 60 giay trong cache
de nhieu nguoi mo trang khong don yeu cau qua tunnel. May tat -> tra online=False, khong nem loi."""
from ecentric_workspace.ai_tools.features.ai_voice import constants as C
from ecentric_workspace.ai_tools.features.ai_voice.application import _deps
from ecentric_workspace.ai_tools.features.ai_voice.domain import rules as R
from ecentric_workspace.ai_tools.features.ai_voice.infrastructure.evoice_client import EVoiceDown, EVoiceHttpError

HEALTH_KEY = "ai_voice:health"
BRANDS_KEY = "ai_voice:brands"


class MachineStatusService:
    def __init__(self, settings=None, client=None, cache=None, profiles=None):
        self.settings = settings or _deps.settings()
        self.profiles = profiles or _deps.profiles()
        self.client = client or _deps.client_factory(self.settings)
        self.cache = cache if cache is not None else _deps.cache()

    def execute(self, roles, fresh=False):
        R.require_user(roles)
        hit = None if fresh else self.cache.get_value(HEALTH_KEY)
        if hit:
            return hit
        out = {"online": False, "ready": False, "engine": "", "voices": 0, "message": ""}
        try:
            h = self.client(timeout=10).health() or {}
            out.update({"online": True, "ready": bool(h.get("ready")), "engine": str(h.get("engine") or "")[:200],
                        "voices": int(h.get("voices") or 0)})
        except C.AiVoiceError as e:
            out["message"] = str(e)
        except EVoiceDown:
            out["message"] = C.Msg.DOWN
        except EVoiceHttpError as e:
            out["message"] = ("Máy giọng đọc từ chối token - kiểm tra Cài đặt." if e.status in (401, 403)
                              else e.detail)
        self.cache.set_value(HEALTH_KEY, out, expires_in_sec=30)
        return out

    def brands(self, user, roles):
        """Chi liet ke brand ma giong dang dung CO trong thu vien ERP va nguoi nay duoc dung (dong y + han che).
        Cache giu ban tho tu may (chung moi nguoi), loc theo nguoi xem moi lan."""
        R.require_user(roles)
        rows = self.cache.get_value(BRANDS_KEY)
        if rows is None:
            try:
                rows = [{"name": str(b.get("name") or "")[:80], "current": str(b.get("current") or ""),
                         "current_name": str(b.get("current_name") or "")[:80]}
                        for b in self.client(timeout=10).brands() if b.get("name") and b.get("current")]
            except (C.AiVoiceError, EVoiceDown, EVoiceHttpError):
                return {"online": False, "brands": []}
            self.cache.set_value(BRANDS_KEY, rows, expires_in_sec=60)
        out = []
        for b in rows:
            p = self.profiles.get_by_voice_id(b["current"])
            if p and p.get("consent_by") and p.get("consent_date") and R.can_use_profile(p, user, roles):
                out.append({"name": b["name"], "current_name": p.get("voice_name") or b["current_name"]})
        return {"online": True, "brands": out, "hidden": len(rows) - len(out)}
