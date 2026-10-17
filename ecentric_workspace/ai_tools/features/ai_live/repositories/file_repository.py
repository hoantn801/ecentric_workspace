# Copyright (c) 2026, eCentric and contributors
"""Doc File cua Frappe (chu so huu, noi dung) cho Bo live / Studio anh host."""


class FileRepository:
    def owner(self, file_url):
        import frappe
        return frappe.db.get_value("File", {"file_url": file_url}, "owner")

    def content(self, file_url):
        import frappe
        name = frappe.db.get_value("File", {"file_url": file_url}, "name")
        if not name:
            return None
        return frappe.get_doc("File", name).get_content()
