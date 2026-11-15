# Copyright (c) 2026, eCentric and contributors
"""p380_ai_voice_trang_moi (15/11/2026): Giong doc AI /ai-voice (eVoice tren ERP).
- Khoi tao EC AI Voice Settings (dia chi mac dinh https://voice.ecentric.asia, chua co token -> trang bao
  "chua cai dat" cho toi khi System Manager dan token).
- Tao Web Page /ai-voice "Giong doc AI".
- Dong bo lai VO SHELL TINH (menu fallback) cua /ai-video, /ai-live, /ai-usage: them muc "Giong doc AI".
  Menu song do server ve nen da doi ngay khi deploy; phan nay chi cho lan ve dau khong lech.
Moi buoc tu bat loi, buoc nay loi khong chan buoc kia. Chay lai vo hai."""
import frappe

from ecentric_workspace.ai_tools.pages.ai_live import page_sync as live_sync
from ecentric_workspace.ai_tools.pages.ai_usage import page_sync as usage_sync
from ecentric_workspace.ai_tools.pages.ai_video import page_sync as video_sync
from ecentric_workspace.ai_tools.pages.ai_voice import page_sync as voice_sync


def _settings():
    if not frappe.db.exists("DocType", "EC AI Voice Settings"):
        return
    doc = frappe.get_single("EC AI Voice Settings")
    if doc.get("base_url"):
        return
    doc.base_url = "https://voice.ecentric.asia"
    doc.default_quality = doc.get("default_quality") or "quality_fast"
    doc.default_speed = doc.get("default_speed") or 1.1
    doc.timeout = doc.get("timeout") or 30
    doc.save(ignore_permissions=True)


def execute():
    try:
        _settings()
    except Exception:
        frappe.log_error(title="p380_ai_voice_trang_moi settings")
    if not frappe.db.exists("DocType", "Web Page"):
        return
    for name, mod in (("ai-voice", voice_sync), ("ai-video", video_sync), ("ai-live", live_sync), ("ai-usage", usage_sync)):
        try:
            frappe.logger("ai_tools").info("p380_ai_voice_trang_moi %s: %s" % (name, mod.sync() or {}))
        except Exception:
            frappe.log_error(title="p380_ai_voice_trang_moi " + name)
