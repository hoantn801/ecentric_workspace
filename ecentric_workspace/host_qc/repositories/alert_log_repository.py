# Copyright (c) 2026, eCentric and contributors
"""Host QC Alert Log - khoa idem_key unique: trung thi khong gui lai."""
import frappe

from ecentric_workspace.host_qc.constants import doctypes as DT


class AlertLogRepository:
    def exists(self, idem_key):
        return bool(frappe.db.exists(DT.ALERT_LOG, {"idem_key": idem_key}))

    def insert(self, values):
        doc = frappe.get_doc(dict(values, doctype=DT.ALERT_LOG))
        doc.flags.ignore_permissions = True
        try:
            doc.insert()
        except frappe.DuplicateEntryError:
            return None                      # hai request song song cung khoa: ban kia da ghi
        return doc.name
