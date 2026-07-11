# Copyright (c) 2026, eCentric and contributors
"""ERP user <-> SCTS identity mapping. The ONLY source of userId/SignatureId for provider
calls (frontend never supplies identity). One ACTIVE mapping per (user, environment).
Verification is an SM-gated action; stores safe metadata only - never signature images,
never HSM IDs."""
import frappe
from frappe import _
from frappe.model.document import Document


class ECSCTSUserMapping(Document):
    def validate(self):
        if self.active:
            dup = frappe.db.exists("EC SCTS User Mapping", {
                "frappe_user": self.frappe_user, "environment": self.environment,
                "active": 1, "name": ["!=", self.name or ""]})
            if dup:
                frappe.throw(_("An active mapping already exists for {0} ({1}): {2}").format(
                    self.frappe_user, self.environment, dup))
        if self.mapping_status == "Verified" and not self.verified_at:
            frappe.throw(_("Verified mappings must carry verification metadata (use the admin verify action)."))
