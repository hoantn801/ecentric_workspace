# Copyright (c) 2026, eCentric and contributors
"""Doc EC AI Live Alert Settings (Single). Chi noi nay giai ma Password (webhook Teams, token Zalo)."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C


class AlertSettingsRepository:
    def get(self, with_secrets=False):
        import frappe
        doc = frappe.get_single(C.ALERT_SETTINGS)
        d = {"enabled": int(doc.enabled or 0), "teams_enabled": int(doc.teams_enabled or 0),
             "teams_format": doc.teams_format or C.TEAMS_FORMATS[0], "zalo_enabled": int(doc.zalo_enabled or 0),
             "zalo_chat_id": doc.zalo_chat_id or "", "zalo_api_base": doc.zalo_api_base or C.ZALO_API_BASE,
             "zalo_send_path": doc.zalo_send_path or C.ZALO_SEND_PATH,
             "dead_man_min": int(doc.dead_man_minutes or C.DEAD_MAN_MIN),
             "dedupe_min": int(doc.dedupe_minutes or C.DEDUPE_MIN),
             "escalate_min": int(doc.escalate_minutes or C.ESCALATE_MIN)}
        if with_secrets:
            d["teams_webhook_url"] = doc.get_password("teams_webhook_url", raise_exception=False) or ""
            d["zalo_bot_token"] = doc.get_password("zalo_bot_token", raise_exception=False) or ""
        return d
