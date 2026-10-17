# Copyright (c) 2026, eCentric and contributors
"""Truy van EC AI Live Machine + User may phat (token API Frappe = api_key:api_secret)."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C


class MachineRepository:
    def by_user(self, user):
        import frappe
        name = frappe.db.get_value(C.MACHINE, {"user": user}, "name")
        return self.get(name) if name else None

    def get(self, code):
        import frappe
        if not code or not frappe.db.exists(C.MACHINE, code):
            return None
        doc = frappe.get_doc(C.MACHINE, code)
        return {"machine_code": doc.name, "label": doc.label, "enabled": int(doc.enabled or 0),
                "user": doc.user, "brands": doc.brands or ""}

    def upsert(self, code, label, brands):
        import frappe
        if frappe.db.exists(C.MACHINE, code):
            doc = frappe.get_doc(C.MACHINE, code)
        else:
            doc = frappe.get_doc({"doctype": C.MACHINE, "machine_code": code, "enabled": 1})
        if label is not None:
            doc.label = label
        if brands is not None:
            doc.brands = brands
        doc.save(ignore_permissions=True) if not doc.is_new() else doc.insert(ignore_permissions=True)
        return doc.name

    def ensure_user(self, code):
        """User Website (khong vao Desk) cho may phat; tra ten user."""
        import frappe
        email = C.MACHINE_EMAIL % code.lower()
        if not frappe.db.exists("User", email):
            frappe.get_doc({"doctype": "User", "email": email, "first_name": "AI Live %s" % code,
                            "user_type": "Website User", "send_welcome_email": 0, "enabled": 1}).insert(ignore_permissions=True)
        frappe.db.set_value(C.MACHINE, code, "user", email)
        return email

    def rotate_keys(self, user):
        """Tao api_key/api_secret moi cho user may phat. Tra 'key:secret' (chi hien 1 lan)."""
        import frappe
        doc = frappe.get_doc("User", user)
        key, secret = frappe.generate_hash(length=15), frappe.generate_hash(length=15)
        doc.api_key = key
        doc.api_secret = secret
        doc.save(ignore_permissions=True)
        return "%s:%s" % (key, secret)
