# Copyright (c) 2026, eCentric and contributors
"""Truy van EC AI Voice Job (phieu giong doc)."""
from ecentric_workspace.ai_tools.features.ai_voice import constants as C

LIST_FIELDS = ["name", "title", "voice_key", "voice_label", "quality", "speed", "language", "status", "progress",
               "position", "chars", "seconds", "gen_seconds", "audio_file", "error", "owner", "creation",
               "submitted_at", "finished_at", "evoice_job_id", "cancel_requested"]
FULL_FIELDS = LIST_FIELDS + ["text", "voice_profile", "breath", "attempts", "fetch_attempts", "last_polled_at",
                             "last_error", "modified", "started_at", "callback_url"]


class JobRepository:
    def insert(self, values):
        import frappe
        doc = frappe.get_doc(dict(values, doctype=C.JOB))
        doc.insert(ignore_permissions=True)
        return doc.name

    def get(self, name, for_update=False):
        import frappe
        if not name:
            return None
        row = frappe.db.get_value(C.JOB, name, FULL_FIELDS, as_dict=True, for_update=for_update)
        return _clean(row)

    def find_by_remote_id(self, evoice_job_id, for_update=False):
        import frappe
        if not evoice_job_id:
            return None
        name = frappe.db.get_value(C.JOB, {"evoice_job_id": evoice_job_id}, "name")
        return self.get(name, for_update=for_update) if name else None

    def update(self, name, values):
        """Ghi thang (khong qua controller) - phieu chi doi trang thai, khong co rang buoc nghiep vu o controller."""
        import frappe
        frappe.db.set_value(C.JOB, name, values, update_modified=True)

    def delete(self, name):
        import frappe
        frappe.delete_doc(C.JOB, name, ignore_permissions=True, force=True)

    def list(self, owner=None, statuses=None, limit=C.LIST_LIMIT, start=0):
        import frappe
        filters = {}
        if owner:
            filters["owner"] = owner
        if statuses:
            filters["status"] = ["in", list(statuses)]
        rows = frappe.get_all(C.JOB, filters=filters, fields=LIST_FIELDS, order_by="creation desc",
                              limit_start=int(start or 0), limit_page_length=int(limit or C.LIST_LIMIT))
        return [_clean(r) for r in rows]

    def count_active(self, owner):
        """Khoa dong User truoc khi dem -> 2 yeu cau tao cung luc khong vuot tran (QC 15/11)."""
        import frappe
        frappe.db.get_value("User", owner, "name", for_update=True)
        return frappe.db.count(C.JOB, {"owner": owner, "status": ["in", list(C.JobStatus.ACTIVE)]})

    def active_names(self):
        """Phieu chua xong + phieu xong ma chua tai file ve (job nen poll)."""
        import frappe
        a = frappe.get_all(C.JOB, filters={"status": ["in", list(C.JobStatus.ACTIVE)]}, pluck="name",
                           order_by="creation asc", limit_page_length=500)
        b = frappe.get_all(C.JOB, filters={"status": C.JobStatus.DONE, "audio_file": ["is", "not set"]},
                           pluck="name", order_by="creation asc", limit_page_length=200)
        return list(dict.fromkeys(a + b))


def _clean(r):
    if not r:
        return None
    d = dict(r)
    for k in ("creation", "modified", "submitted_at", "finished_at", "last_polled_at", "started_at"):
        if d.get(k) is not None:
            d[k] = str(d[k])
    for k in ("position", "chars", "attempts", "fetch_attempts", "cancel_requested", "breath"):
        if k in d:
            d[k] = int(d.get(k) or 0)
    for k in ("speed", "seconds", "gen_seconds"):
        if k in d and d.get(k) is not None:
            d[k] = float(d[k])
    return d
