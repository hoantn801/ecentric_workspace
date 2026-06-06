# Copyright (c) 2026, eCentric
# Alert Center Phase B (ALERT_CENTER/01_PHASE_B_PLAN.md). Schema layer only -
# business logic (price check / dedupe / actions) lands in Phase C services.

import frappe
from frappe import _
from frappe.model.document import Document


class ECMarketplaceOrderLog(Document):
    def before_insert(self):
        self.set_order_key()

    def validate(self):
        self.set_order_key()

    def set_order_key(self):
        if self.source_system and self.external_order_id:
            self.order_key = "{0}|{1}".format(self.source_system, self.external_order_id.strip())
