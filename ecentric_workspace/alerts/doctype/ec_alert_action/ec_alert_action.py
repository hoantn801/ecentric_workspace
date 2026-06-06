# Copyright (c) 2026, eCentric
# Alert Center Phase B (ALERT_CENTER/01_PHASE_B_PLAN.md). Schema layer only -
# business logic (price check / dedupe / actions) lands in Phase C services.

import frappe
from frappe import _
from frappe.model.document import Document


class ECAlertAction(Document):
    def before_insert(self):
        if not self.requested_at:
            self.requested_at = frappe.utils.now_datetime()
