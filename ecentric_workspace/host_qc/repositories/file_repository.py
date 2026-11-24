# Copyright (c) 2026, eCentric and contributors
"""Luu tep RIENG TU (clip, chep loi) dinh vao ban ghi - chi nguoi doc duoc ban ghi moi tai duoc tep."""
import frappe

from ecentric_workspace.host_qc.constants import doctypes as DT


class FileRepository:
    def save_private(self, doctype, name, fieldname, filename, content):
        doc = frappe.get_doc({"doctype": DT.FILE, "file_name": filename, "is_private": 1,
                              "attached_to_doctype": doctype, "attached_to_name": name,
                              "attached_to_field": fieldname, "content": content})
        doc.flags.ignore_permissions = True
        doc.insert()
        return doc.file_url
