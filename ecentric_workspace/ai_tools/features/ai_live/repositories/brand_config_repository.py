# Copyright (c) 2026, eCentric and contributors
"""Truy van EC AI Live Brand Config. Chi noi nay doc/ghi DB va giai ma Password."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C


class BrandConfigRepository:
    def get(self, brand, with_keys=False):
        """dict cau hinh brand (khoa da giai ma neu with_keys) hoac None."""
        import frappe
        if not frappe.db.exists(C.BRAND_CONFIG, brand):
            return None
        doc = frappe.get_doc(C.BRAND_CONFIG, brand)
        d = {"brand": doc.name, "brand_name": doc.brand_name, "enabled": int(doc.enabled or 0),
             "updated_at": str(doc.modified or "")}
        for f in C.PLAIN_FIELDS:
            d[f] = doc.get(f)
        for f in C.SETTING_FIELDS.values():
            d[f] = doc.get(f)
        if with_keys:
            for f in C.KEY_FIELDS:
                d[f] = doc.get_password(f, raise_exception=False) or ""
        return d

    def list_names(self):
        import frappe
        return [r.name for r in frappe.get_all(C.BRAND_CONFIG, fields=["name"], order_by="name asc")]

    def set_settings(self, brand, values):
        """values: {templates_json|playlist_json|cooldowns_json: chuoi JSON}."""
        import frappe
        doc = frappe.get_doc(C.BRAND_CONFIG, brand)
        for k, v in values.items():
            doc.set(k, v)
        doc.save(ignore_permissions=True)
        return str(doc.modified or "")
