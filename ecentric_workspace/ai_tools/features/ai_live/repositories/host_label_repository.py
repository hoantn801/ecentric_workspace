# Copyright (c) 2026, eCentric and contributors
"""Ten hien thi cua host trong Kho host (may chay video chi biet ma host)."""
import json

from ecentric_workspace.ai_tools.features.ai_live import constants as C


class HostLabelRepository:
    def all(self):
        import frappe
        try:
            return json.loads(frappe.db.get_default(C.HOST_LABELS_KEY) or "{}")
        except ValueError:
            return {}

    def set(self, host, label):
        import frappe
        d = self.all()
        d[host] = label
        frappe.db.set_default(C.HOST_LABELS_KEY, json.dumps(d, ensure_ascii=False))
