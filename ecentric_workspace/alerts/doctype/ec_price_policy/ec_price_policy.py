# Copyright (c) 2026, eCentric
# Alert Center Phase B (ALERT_CENTER/01_PHASE_B_PLAN.md). Schema layer only -
# business logic (price check / dedupe / actions) lands in Phase C services.

import frappe
from frappe import _
from frappe.model.document import Document

# Scope-key + overlap are the SINGLE SOURCE OF TRUTH in services.policy_scope so
# the controller guard and the bulk-import Conflict preview never diverge.
from ecentric_workspace.alerts.services.policy_scope import (
    scope_key as _scope_key, windows_overlap as _windows_overlap)
from ecentric_workspace.alerts.services import policy_validation


class ECPricePolicy(Document):
    def validate(self):
        # Shape: lookup priority 6 (brand-level fallback) must be explicit opt-in.
        if not (self.item or self.seller_sku or self.shop) and not self.is_brand_fallback:
            frappe.throw(
                _("Policy must target an Item, Seller SKU or Shop - or be explicitly marked 'Is Brand-level Fallback'.")
            )
        # Field rules via the SINGLE shared validator (no duplicate rules here).
        # Active => full completeness; Draft/Paused/Inactive => range-if-present.
        errs = policy_validation.validate_policy_values(
            {"min_price": self.min_price, "high_alert_percent": self.high_alert_percent,
             "severe_drop_percent": self.severe_drop_percent,
             "effective_from": self.effective_from, "effective_to": self.effective_to},
            require_complete=((self.status or "") == "Active"))
        if errs:
            frappe.throw("; ".join(errs))
        self._guard_exact_scope_conflict()

    def _guard_exact_scope_conflict(self):
        """G2.x Policy Conflict Guard: refuse a 2nd Active policy with the EXACT
        same scope (brand + platform + shop + seller_sku/item, normalized) and
        OVERLAPPING validity. Platform=All is a DIFFERENT scope from a specific
        platform (so it is NOT blocked - it is the fallback that a specific
        policy overrides). Fires on Desk + the api_policies path (both save())."""
        if (self.status or "") != "Active":
            return
        my = _scope_key(self.platform, self.shop, self.seller_sku, self.item,
                        self.is_brand_fallback)
        narrow = {"brand": self.brand, "status": "Active"}
        if self.seller_sku:
            narrow["seller_sku"] = self.seller_sku
        elif self.item:
            narrow["item"] = self.item
        else:
            narrow["is_brand_fallback"] = 1
        rows = frappe.get_all(
            "EC Price Policy", filters=narrow,
            fields=["name", "platform", "shop", "seller_sku", "item",
                    "is_brand_fallback", "effective_from", "effective_to"])
        for r in rows:
            if r.name == (self.name or ""):
                continue
            if _scope_key(r.platform, r.shop, r.seller_sku, r.item,
                          r.is_brand_fallback) != my:
                continue
            if _windows_overlap(self.effective_from, self.effective_to,
                                r.effective_from, r.effective_to):
                frappe.throw(
                    _("An Active price policy with the EXACT same scope already "
                      "exists: {0} (brand {1} / platform {2} / shop {3} / SKU {4}), "
                      "with overlapping validity. Two Active policies of the same "
                      "scope are ambiguous. Inactivate the other one first, or "
                      "narrow the scope. (Platform=All is a fallback that a more "
                      "specific platform/shop policy overrides - that is allowed.)"
                      ).format(r.name, self.brand, self.platform or "All",
                               self.shop or "-",
                               self.seller_sku or self.item or "(fallback)"),
                    title=_("Duplicate Active Policy"))
