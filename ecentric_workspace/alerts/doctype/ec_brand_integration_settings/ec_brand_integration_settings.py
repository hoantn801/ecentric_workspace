# Copyright (c) 2026, eCentric
# Alert Center Phase B (ALERT_CENTER/01_PHASE_B_PLAN.md). Schema layer only -
# business logic (price check / dedupe / actions) lands in Phase C services.

import frappe
from frappe import _
from frappe.model.document import Document


class ECBrandIntegrationSettings(Document):
    def validate(self):
        # One settings record per (brand, integration_type).
        dup = frappe.db.exists(
            "EC Brand Integration Settings",
            {
                "brand": self.brand,
                "integration_type": self.integration_type,
                "name": ("!=", self.name),
            },
        )
        if dup:
            frappe.throw(
                _("Integration settings for brand {0} / {1} already exist: {2}").format(
                    self.brand, self.integration_type, dup
                )
            )
