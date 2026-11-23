# Copyright (c) 2026, eCentric and contributors
"""Doc / ghi Host QC Settings (Single).

Dung frappe.get_cached_doc: Frappe tu xoa cache khi luu trang Settings, nen KHONG can singleton rieng
(frappe-rules muc 6 chi bat invalidate() cho singleton tu viet)."""
import frappe

from ecentric_workspace.host_qc.constants import doctypes as DT

PASSWORDS = ("kie_api_key", "claude_api_key", "sharepoint_client_secret")


class SettingsRepository:
    def get(self):
        d = frappe.get_cached_doc(DT.SETTINGS).as_dict()
        for k in PASSWORDS:
            d.pop(k, None)
        return d

    def secret(self, fieldname):
        """Khoa (Password) - chi goi o service tra cho may da xac thuc. Khong log."""
        doc = frappe.get_cached_doc(DT.SETTINGS)
        return doc.get_password(fieldname, raise_exception=False) or ""

    def set_rules_version(self, version):
        frappe.db.set_single_value(DT.SETTINGS, "rules_version", version)
        frappe.clear_document_cache(DT.SETTINGS, DT.SETTINGS)

    def set_defaults(self, values):
        """Chi dien o con trong (patch khoi tao) - khong ghi de gia tri Production da sua."""
        doc = frappe.get_single(DT.SETTINGS)
        changed = False
        for k, v in values.items():
            if doc.get(k) in (None, "", 0):
                doc.set(k, v)
                changed = True
        if changed:
            doc.flags.ignore_permissions = True
            doc.save()
        return changed
