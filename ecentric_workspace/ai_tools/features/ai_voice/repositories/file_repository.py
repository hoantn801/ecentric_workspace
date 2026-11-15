# Copyright (c) 2026, eCentric and contributors
"""File cua Frappe cho Giong doc AI: doc file mau nguoi dung tai len, luu MP3 ket qua (private)."""


class FileRepository:
    def info(self, file_url):
        """{name, owner, file_name, size} hoac None."""
        import frappe
        if not file_url:
            return None
        r = frappe.db.get_value("File", {"file_url": file_url}, ["name", "owner", "file_name", "file_size"], as_dict=True)
        if not r:
            return None
        return {"name": r.name, "owner": r.owner, "file_name": r.file_name or "", "size": int(r.file_size or 0)}

    def content(self, file_url):
        import frappe
        name = frappe.db.get_value("File", {"file_url": file_url}, "name")
        if not name:
            return None
        return frappe.get_doc("File", name).get_content()

    def save(self, file_name, content, doctype, docname, fieldname=None):
        import frappe
        f = frappe.get_doc({"doctype": "File", "file_name": file_name, "is_private": 1, "content": content,
                            "attached_to_doctype": doctype, "attached_to_name": docname,
                            "attached_to_field": fieldname})
        f.save(ignore_permissions=True)
        return f.file_url

    def delete(self, file_url):
        import frappe
        if not file_url:
            return
        for name in frappe.get_all("File", filters={"file_url": file_url}, pluck="name"):
            frappe.delete_doc("File", name, ignore_permissions=True, force=True)
