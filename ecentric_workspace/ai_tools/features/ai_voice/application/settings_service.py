# Copyright (c) 2026, eCentric and contributors
"""Cai dat ket noi may giong doc (System Manager): dia chi, token (chi ghi - khong bao gio tra ve trang),
chat luong / toc do mac dinh, kiem tra ket noi (/health co token)."""
from ecentric_workspace.ai_tools.features.ai_voice import constants as C
from ecentric_workspace.ai_tools.features.ai_voice.application import _deps
from ecentric_workspace.ai_tools.features.ai_voice.domain import rules as R
from ecentric_workspace.ai_tools.features.ai_voice.infrastructure.evoice_client import EVoiceDown, EVoiceHttpError


class SettingsService:
    def __init__(self, settings=None, client=None, cache=None):
        self.settings = settings or _deps.settings()
        self.client = client or _deps.client_factory(self.settings)
        self.cache = cache if cache is not None else _deps.cache()

    def get(self, roles):
        R.require_admin(roles)
        s = self.settings.get()
        return {k: s.get(k) for k in ("base_url", "token_set", "default_quality", "default_speed", "timeout",
                                      "callback_base_url", "last_check_at", "last_check_result")}

    def save(self, roles, payload):
        R.require_admin(roles)
        payload = payload or {}
        values = {"base_url": R.norm_base_url(payload.get("base_url") or C.DEFAULT_BASE_URL),
                  "default_quality": R.norm_quality(payload.get("default_quality")),
                  "default_speed": R.norm_speed(payload.get("default_speed"))}
        cb = str(payload.get("callback_base_url") or "").strip()
        values["callback_base_url"] = R.norm_base_url(cb) if cb else ""
        try:
            values["timeout"] = min(max(int(payload.get("timeout") or C.DEFAULT_TIMEOUT), 5), 120)
        except (TypeError, ValueError):
            values["timeout"] = C.DEFAULT_TIMEOUT
        token = payload.get("token")
        token = str(token).strip() if token not in (None, "") else None
        self.settings.save(values, token=token)
        self._forget()
        return self.get(roles)

    def test(self, roles):
        R.require_admin(roles)
        self._forget()
        try:
            h = self.client(timeout=15).health() or {}
            ok = True
            msg = "Kết nối được. Máy %s - %s giọng - %s" % (
                "sẵn sàng" if h.get("ready") else "chưa sẵn sàng", h.get("voices", 0), str(h.get("engine") or "")[:120])
        except C.AiVoiceError as e:
            ok, msg = False, str(e)
        except EVoiceDown as e:
            ok, msg = False, "%s (%s)" % (C.Msg.DOWN, e)
        except EVoiceHttpError as e:
            ok, msg = False, ("Sai token (máy từ chối): %s" % e.detail) if e.status in (401, 403) else e.detail
        self.settings.mark_check(("OK: " if ok else "LỖI: ") + msg)
        return {"ok": ok, "message": msg}

    def _forget(self):
        try:
            self.cache.delete_value("ai_voice:health")
            self.cache.delete_value("ai_voice:brands")
        except Exception:  # noqa: BLE001
            pass
