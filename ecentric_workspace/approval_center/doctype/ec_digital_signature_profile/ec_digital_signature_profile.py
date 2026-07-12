# Copyright (c) 2026, eCentric and contributors
"""Per-form signing enablement + provider targets + level/field/transition maps.
Generic layer: enabling a new form = a new profile row, zero provider-specific code."""
import frappe
from frappe import _
from frappe.model.document import Document


class ECDigitalSignatureProfile(Document):
    def validate(self):
        seen = set()
        for row in (self.levels or []):
            if row.level_no in seen:
                frappe.throw(_("Duplicate signing level {0} in profile.").format(row.level_no))
            seen.add(row.level_no)
        if self.enabled and not any((r.requires_signature for r in (self.levels or []))):
            frappe.throw(_("An enabled profile needs at least one level with requires_signature."))
        if self.deadline_rule == "Fixed Days" and not (self.deadline_days or 0) > 0:
            frappe.throw(_("deadline_days required for Fixed Days rule."))
        if self.deadline_rule == "From Field" and not (self.deadline_source or "").strip():
            frappe.throw(_("deadline_source required for From Field rule."))
