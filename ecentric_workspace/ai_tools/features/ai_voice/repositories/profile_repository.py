# Copyright (c) 2026, eCentric and contributors
"""Truy van EC AI Voice Profile (thu vien giong tren ERP)."""
from ecentric_workspace.ai_tools.features.ai_voice import constants as C

FIELDS = ["name", "voice_id", "voice_name", "gender", "description", "brand", "owner_user", "restricted",
          "status", "source", "consent_by", "consent_date", "consent_note", "consent_file", "sample_file",
          "ref_text", "clip_seconds", "upload_error", "upload_file", "upload_started_at", "missing_on_server",
          "last_synced", "owner", "creation", "modified"]


class ProfileRepository:
    def list(self, include_inactive=False):
        import frappe
        filters = {} if include_inactive else {"status": C.VoiceStatus.ACTIVE}
        rows = frappe.get_all(C.PROFILE, filters=filters, fields=FIELDS, order_by="voice_name asc", limit_page_length=0)
        return [_clean(r) for r in rows]

    def get(self, name):
        import frappe
        if not name or not frappe.db.exists(C.PROFILE, name):
            return None
        return _clean(frappe.db.get_value(C.PROFILE, name, FIELDS, as_dict=True))

    def get_by_voice_id(self, voice_id):
        import frappe
        if not voice_id:
            return None
        name = frappe.db.get_value(C.PROFILE, {"voice_id": voice_id}, "name")
        return self.get(name) if name else None

    def known_voice_ids(self):
        import frappe
        return {r.voice_id for r in frappe.get_all(C.PROFILE, fields=["voice_id"], limit_page_length=0) if r.voice_id}

    def insert(self, values):
        import frappe
        doc = frappe.get_doc(dict(values, doctype=C.PROFILE))
        doc.insert(ignore_permissions=True)
        return doc.name

    def update(self, name, values):
        import frappe
        doc = frappe.get_doc(C.PROFILE, name)
        for k, v in values.items():
            doc.set(k, v)
        doc.save(ignore_permissions=True)

    def delete(self, name):
        import frappe
        frappe.delete_doc(C.PROFILE, name, ignore_permissions=True, force=True)

    def lock(self, name):
        """SELECT ... FOR UPDATE: tranh 2 job nen cung xu ly mot giong."""
        import frappe
        return frappe.db.get_value(C.PROFILE, name, "status", for_update=True)


def _clean(r):
    if not r:
        return None
    d = dict(r)
    for k in ("consent_date", "last_synced", "upload_started_at", "creation", "modified"):
        if d.get(k) is not None:
            d[k] = str(d[k])
    d["restricted"] = int(d.get("restricted") or 0)
    d["missing_on_server"] = int(d.get("missing_on_server") or 0)
    return d
