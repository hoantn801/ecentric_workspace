# Copyright (c) 2026, eCentric and contributors
"""EC Approval SLA Policy - shared, reusable SLA config (outside the 7 core)."""
import frappe
from frappe import _
from frappe.model.document import Document


class ECApprovalSLAPolicy(Document):
    def validate(self):
        if not self.is_new():
            before = self.get_doc_before_save()
            if before and before.policy_code and before.policy_code != self.policy_code:
                frappe.throw(_("policy_code is immutable."))
        if self.use_business_hours:
            frappe.throw(_("Business-hours SLA calculation is not supported yet (B1). "
                           "Uncheck 'use_business_hours'; only calendar/elapsed hours are computed."))
