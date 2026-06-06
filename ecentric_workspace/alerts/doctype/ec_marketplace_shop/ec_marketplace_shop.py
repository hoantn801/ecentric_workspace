# Copyright (c) 2026, eCentric
# Alert Center Phase B (ALERT_CENTER/01_PHASE_B_PLAN.md). Schema layer only -
# business logic (price check / dedupe / actions) lands in Phase C services.

import frappe
from frappe import _
from frappe.model.document import Document


class ECMarketplaceShop(Document):
    def validate(self):
        if self.omisell_shop_id:
            self.omisell_shop_id = self.omisell_shop_id.strip()
