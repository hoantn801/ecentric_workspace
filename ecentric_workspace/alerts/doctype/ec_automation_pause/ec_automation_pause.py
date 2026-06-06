# Copyright (c) 2026, eCentric
# Alert Center Phase B (ALERT_CENTER/01_PHASE_B_PLAN.md). Schema layer only -
# business logic (price check / dedupe / actions) lands in Phase C services.

import frappe
from frappe import _
from frappe.model.document import Document


class ECAutomationPause(Document):
    def validate(self):
        if self.pause_from and self.pause_until and self.pause_until <= self.pause_from:
            frappe.throw(_("Pause Until must be after Pause From."))

    def before_insert(self):
        if not self.paused_by:
            self.paused_by = frappe.session.user
