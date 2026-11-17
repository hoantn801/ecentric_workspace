# Copyright (c) 2026, eCentric and contributors
"""EC License Settings (Single): cong tac + khoa bi mat. Khoa CHI doc bang get_password trong service cap license;
khong bao gio tra ra trang / log."""
from ecentric_workspace.ai_tools.features.ai_live import license_constants as L

_SECRET_FIELD = {"elive": "elive_secret", "esync": "esync_secret", "evoice": "evoice_secret"}


def _pwd(field):
    from frappe.utils.password import get_decrypted_password
    try:
        return get_decrypted_password(L.SETTINGS, L.SETTINGS, field, raise_exception=False) or ""
    except Exception:  # chua co / encryption_key doi -> coi nhu thieu, khong lo loi
        return ""


class LicenseSettingsRepository:
    def get(self):
        import frappe
        if not frappe.db.exists("DocType", L.SETTINGS):
            return {"enabled": 0, "log_only": 1, "office_ips": "", "teams_format": "workflows", "killed": 1}
        v = frappe.db.get_singles_dict(L.SETTINGS) or {}
        return {"enabled": int(v.get("enabled") or 0), "log_only": int(v.get("log_only") or 0),
                "office_ips": v.get("office_ips") or "", "teams_format": v.get("teams_format") or "workflows",
                "killed": int(bool(frappe.conf.get(L.KILL_SWITCH)))}

    def secret(self, product):
        return _pwd(_SECRET_FIELD[product])

    def dist_secret(self):
        return _pwd("dist_secret").strip()

    def teams_webhook(self):
        return _pwd("teams_webhook").strip()

    def set_mode(self, enabled, log_only):
        import frappe
        doc = frappe.get_single(L.SETTINGS)
        doc.enabled, doc.log_only = int(bool(enabled)), int(bool(log_only))
        doc.save(ignore_permissions=True)
