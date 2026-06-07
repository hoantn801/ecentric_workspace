# Copyright (c) 2026, eCentric
# Alert Center Phase F (decision F-2). Rule overlay config - engine consults
# Active rules only; hard action matrix stays code-enforced in services.

import frappe
from frappe import _
from frappe.model.document import Document

LOCKABLE_RULES = ("severe_price_drop", "possible_missing_zero")


class ECAlertRule(Document):
    def validate(self):
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            frappe.throw(_("Effective To cannot be before Effective From."))
        if int(self.recommend_stock_lock or 0) and self.rule_code not in LOCKABLE_RULES:
            frappe.throw(_(
                "Recommend Stock Lock is only allowed for severe_price_drop / "
                "possible_missing_zero (hard action matrix - {0} can never lock)."
            ).format(self.rule_code))
        if self.threshold_percent and float(self.threshold_percent) < 0:
            frappe.throw(_("Threshold Percent cannot be negative."))
