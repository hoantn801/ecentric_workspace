# Copyright (c) 2026, eCentric and contributors
"""Doc EC AI Live Alert Settings (Single). Chi noi nay giai ma Password (webhook Teams, token Zalo).
fix10f: them nguong may im lang + bang kenh theo nhom / brand (EC AI Live Alert Channel)."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C


def _channel(row, with_secrets):
    d = {"enabled": int(row.enabled or 0), "group_name": row.group_name or "", "brands": row.brands or "",
         "teams_enabled": int(row.teams_enabled or 0), "teams_format": row.teams_format or "",
         "zalo_enabled": int(row.zalo_enabled or 0), "zalo_chat_id": row.zalo_chat_id or ""}
    if with_secrets:
        d["teams_webhook_url"] = row.get_password("teams_webhook_url", raise_exception=False) or ""
        d["zalo_bot_token"] = row.get_password("zalo_bot_token", raise_exception=False) or ""
    return d


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
             "escalate_min": int(doc.escalate_minutes or C.ESCALATE_MIN),
             "machine_offline_min": int(doc.get("machine_offline_minutes") or C.MACHINE_OFFLINE_MIN),
             "machine_repeat_min": int(doc.get("machine_repeat_minutes") or C.MACHINE_REPEAT_MIN),
             "night_repeat_min": int(doc.get("night_repeat_minutes") or C.NIGHT_REPEAT_MIN),
             "night_start": doc.get("night_start") or C.NIGHT_START, "night_end": doc.get("night_end") or C.NIGHT_END,
             "channels": [_channel(r, with_secrets) for r in (doc.get("channels") or [])]}
        if with_secrets:
            d["teams_webhook_url"] = doc.get_password("teams_webhook_url", raise_exception=False) or ""
            d["zalo_bot_token"] = doc.get_password("zalo_bot_token", raise_exception=False) or ""
        return d
