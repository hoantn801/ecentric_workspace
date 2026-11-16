# Copyright (c) 2026, eCentric and contributors
"""Doc / ghi EC AI Voice Settings (Single). Chi noi nay giai ma token (Password)."""
from ecentric_workspace.ai_tools.features.ai_voice import constants as C

PLAIN = ("base_url", "default_quality", "default_speed", "timeout", "callback_base_url")


class SettingsRepository:
    def get(self, with_token=False):
        import frappe
        doc = frappe.get_single(C.SETTINGS)
        d = {k: doc.get(k) for k in PLAIN}
        d["base_url"] = (d.get("base_url") or C.DEFAULT_BASE_URL).rstrip("/")
        d["timeout"] = int(d.get("timeout") or C.DEFAULT_TIMEOUT)
        d["last_check_at"] = str(doc.get("last_check_at") or "")
        d["last_check_result"] = doc.get("last_check_result") or ""
        token = doc.get_password("token", raise_exception=False) or ""
        d["token_set"] = bool(token)
        if with_token:
            d["token"] = token
        return d

    def save(self, values, token=None):
        """values: cac truong thuong. token: None = giu nguyen, chuoi = dat moi."""
        import frappe
        doc = frappe.get_single(C.SETTINGS)
        for k, v in values.items():
            if k in PLAIN:
                doc.set(k, v)
        if token is not None:
            doc.set("token", token)
        doc.save(ignore_permissions=True)

    def mark_check(self, result):
        import frappe
        frappe.db.set_single_value(C.SETTINGS, {"last_check_at": frappe.utils.now_datetime(),
                                                "last_check_result": str(result or "")[:500]})

    def site_url(self):
        import frappe
        return frappe.utils.get_url().rstrip("/")
