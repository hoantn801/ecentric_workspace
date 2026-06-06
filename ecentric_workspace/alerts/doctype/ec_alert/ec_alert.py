# Copyright (c) 2026, eCentric
# Alert Center Phase B (ALERT_CENTER/01_PHASE_B_PLAN.md). Schema layer only -
# business logic (price check / dedupe / actions) lands in Phase C services.

import frappe
from frappe import _
from frappe.model.document import Document


class ECAlert(Document):
    def validate(self):
        if self.status in ("Resolved", "Ignored"):
            if not self.resolved_at:
                self.resolved_at = frappe.utils.now_datetime()
            if not self.resolved_by:
                self.resolved_by = frappe.session.user
        else:
            self.resolved_at = None
            self.resolved_by = None
