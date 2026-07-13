# Copyright (c) 2026, eCentric and contributors
"""Per-form signing enablement + provider targets + level/field/transition maps.
Generic layer: enabling a new form = a new profile row, zero provider-specific code."""
import frappe
from frappe import _
from frappe.model.document import Document


class ECDigitalSignatureProfile(Document):
    def validate(self):
        # Duplicate Selected Level Override rows are always rejected.
        seen = set()
        for row in (self.levels or []):
            if row.level_no in seen:
                frappe.throw(_("Duplicate signing level {0} in profile.").format(row.level_no))
            seen.add(row.level_no)
        # An ENABLED profile must have a governed signing actor consistent with its policy.
        if self.enabled:
            self._validate_enabled_signing_actor()
        # Deadline rules (unchanged).
        if self.deadline_rule == "Fixed Days" and not (self.deadline_days or 0) > 0:
            frappe.throw(_("deadline_days required for Fixed Days rule."))
        if self.deadline_rule == "From Field" and not (self.deadline_source or "").strip():
            frappe.throw(_("deadline_source required for From Field rule."))

    def _validate_enabled_signing_actor(self):
        """Policy-aware signing-actor validation (replaces the legacy 'needs at least one
        requires_signature level' rule which contradicted the policy model).
          * All Approval Levels / Final Approval Level Only -> valid with ZERO override rows;
          * Selected Approval Levels (and legacy blank/unset -> Selected) -> require >= 1
            override row with requires_signature = 1;
          * None -> valid only when a requester signature is required (otherwise the enabled
            profile has no signing actor at all).
        A disabled profile skips this entirely.
        """
        # Legacy blank/unset policy keeps the old behaviour = Selected Approval Levels.
        policy = self.approver_signature_policy or "Selected Approval Levels"
        requester = bool(self.requester_signature_required)
        has_signing_level = any(r.requires_signature for r in (self.levels or []))
        if policy == "Selected Approval Levels":
            if not has_signing_level:
                frappe.throw(_(
                    "Approver Signature Policy 'Selected Approval Levels' needs at least one "
                    "Selected Level Override row with requires_signature."))
        elif policy == "None":
            if not requester:
                frappe.throw(_(
                    "An enabled profile with Approver Signature Policy 'None' must require a "
                    "requester signature - otherwise it has no signing actor."))
        # All Approval Levels / Final Approval Level Only: valid with zero override rows;
        # a requester signature is optional and independently configured.
