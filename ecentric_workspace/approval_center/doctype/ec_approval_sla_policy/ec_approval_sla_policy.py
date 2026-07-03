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
            if not self.business_calendar:
                frappe.throw(_("use_business_hours=1 requires a business_calendar."))
            if not frappe.db.get_value("EC Approval Business Calendar", self.business_calendar, "active"):
                frappe.throw(_("business_calendar '{0}' must exist and be active.").format(self.business_calendar))
            if self.holiday_list and not frappe.db.exists("Holiday List", self.holiday_list):
                frappe.throw(_("holiday_list override '{0}' does not exist.").format(self.holiday_list))
