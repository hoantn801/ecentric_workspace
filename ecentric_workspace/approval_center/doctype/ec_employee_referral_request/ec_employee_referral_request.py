# Copyright (c) 2026, eCentric and contributors
"""EC Employee Referral Request - business data only. Careers Review is a User
participant (NOT a Department). No fulfillment (v1)."""
import re

import frappe
from frappe import _
from frappe.model.document import Document

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ECEmployeeReferralRequest(Document):
    def validate(self):
        if self.candidate_email and not _EMAIL_RE.match((self.candidate_email or "").strip()):
            frappe.throw(_("Email ung vien khong hop le."))
        if self.is_new() or not self.approval_request:
            return
        before = self.get_doc_before_save()
        if before and before.department and before.department != self.department:
            frappe.throw(_("Phong ban la ban chup luc gui va khong the thay doi sau khi gui."))
