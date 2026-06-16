# Copyright (c) 2026, eCentric
# RC7-C Gift/Freebie Price Guard exemption (V1: dedicated gift Seller SKUs only).

import frappe
from frappe import _
from frappe.model.document import Document

from ecentric_workspace.alerts.services import exemption_guard


class ECPriceGuardExemption(Document):
    def validate(self):
        self.seller_sku = (self.seller_sku or "").strip()
        if not self.seller_sku:
            frappe.throw(_("Seller SKU is required."))
        if not self.platform:
            self.platform = "All"
        if (self.effective_from and self.effective_to
                and str(self.effective_to) < str(self.effective_from)):
            frappe.throw(_("Effective To is before Effective From."))
        if not self.exempted_by:
            self.exempted_by = frappe.session.user
        self._guard_overlap()

    def _guard_overlap(self):
        """V1 uniqueness/overlap: no two ACTIVE exemptions for the same
        brand + platform + seller_sku may have overlapping effective windows."""
        if (self.status or "") != "Active":
            return
        rows = frappe.get_all(
            "EC Price Guard Exemption",
            filters={"status": "Active", "brand": self.brand,
                     "platform": self.platform, "seller_sku": self.seller_sku},
            fields=["name", "effective_from", "effective_to"])
        for r in rows:
            if r.name == (self.name or ""):
                continue
            if exemption_guard.windows_overlap(self.effective_from, self.effective_to,
                                               r.effective_from, r.effective_to):
                frappe.throw(
                    _("An active gift exemption with an overlapping window already "
                      "exists for {0} / {1} / {2}: {3}. Adjust the dates or inactivate "
                      "the other one.").format(self.brand, self.platform,
                                               self.seller_sku, r.name),
                    title=_("Overlapping exemption"))
