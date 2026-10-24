# Copyright (c) 2026, eCentric and contributors
"""Truy van EC AI Live Kit (Bo live: SP, FAQ, cau chung, trang thai dung)."""
import json

from ecentric_workspace.ai_tools.features.ai_live import constants as C

FIELDS = ("name", "brand", "title", "host_key", "voice_id", "voice_provider", "mode", "break_sec", "background",
          "bake_bg", "status", "modified", "owner")
JSON_FIELDS = {"products": "products_json", "faq": "faq_json", "generic": "generic_json", "state": "state_json"}


def _j(s, d):
    try:
        return json.loads(s) if s else d
    except ValueError:
        return d


class KitRepository:
    def list(self, brand=None, limit=100):
        import frappe
        filters = {"brand": brand} if brand else {}
        rows = frappe.get_all(C.KIT, filters=filters, fields=list(FIELDS) + ["products_json"],
                              order_by="modified desc", limit_page_length=limit)
        out = []
        for r in rows:
            d = {k: r.get(k) for k in FIELDS}
            d["modified"] = str(d["modified"] or "")
            d["products"] = len(_j(r.get("products_json"), []))
            out.append(d)
        return out

    def get(self, name):
        import frappe
        if not name or not frappe.db.exists(C.KIT, name):
            return None
        doc = frappe.get_doc(C.KIT, name)
        d = {k: doc.get(k) for k in FIELDS}
        d["modified"] = str(d["modified"] or "")
        for k, f in JSON_FIELDS.items():
            d[k] = _j(doc.get(f), {} if k in ("generic", "state") else [])
        return d

    def save(self, name, values):
        """values: truong thuong + products/faq/generic/state (Python) -> tra ten."""
        import frappe
        doc = frappe.get_doc(C.KIT, name) if name else frappe.get_doc({"doctype": C.KIT})
        for k, v in values.items():
            doc.set(JSON_FIELDS.get(k, k), json.dumps(v, ensure_ascii=False) if k in JSON_FIELDS else v)
        if doc.is_new():
            doc.insert(ignore_permissions=True)
        else:
            doc.save(ignore_permissions=True)
        return doc.name
