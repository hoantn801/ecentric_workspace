# Copyright (c) 2026, eCentric and contributors
"""EC Web Push Settings (Single): cong tac + cap khoa VAPID cho web push.

Khoa nam trong DB chu khong nam trong site_config vi doi khoa la viec cua nguoi van
hanh (CnB/IT) chu khong phai cua nguoi co quyen SSH. Khoa bi mat dung fieldtype
Password nen Frappe tu dong ma hoa khi luu va khong tra ve qua REST.
"""
import frappe
from frappe import _
from frappe.model.document import Document


class ECWebPushSettings(Document):
    def validate(self):
        subj = (self.vapid_subject or "").strip()
        if self.enabled:
            if not (self.vapid_public_key or "").strip() or not (self.get_password("vapid_private_key", raise_exception=False) or ""):
                frappe.throw(_("Can co du ca hai khoa VAPID truoc khi bat web push."))
            if not (subj.startswith("mailto:") or subj.startswith("https://")):
                frappe.throw(_("VAPID Subject phai bat dau bang mailto: hoac https://"))
