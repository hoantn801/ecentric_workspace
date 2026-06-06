# Copyright (c) 2026, eCentric
# Alert Center Phase B (ALERT_CENTER/01_PHASE_B_PLAN.md). Schema layer only -
# business logic (price check / dedupe / actions) lands in Phase C services.

import frappe
from frappe import _
from frappe.model.document import Document


class ECPricePolicy(Document):
    def validate(self):
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            frappe.throw(_("Effective To cannot be before Effective From."))
        # Lookup priority 6 (brand-level fallback) must be an explicit opt-in.
        if not (self.item or self.seller_sku or self.shop) and not self.is_brand_fallback:
            frappe.throw(
                _("Policy must target an Item, Seller SKU or Shop - or be explicitly marked 'Is Brand-level Fallback'.")
            )
