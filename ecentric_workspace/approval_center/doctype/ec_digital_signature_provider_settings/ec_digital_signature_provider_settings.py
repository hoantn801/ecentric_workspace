# Copyright (c) 2026, eCentric and contributors
"""Provider settings (per provider x environment). Credentials in encrypted Password fields
(get_password only; persisted via the doc-save path, never db.set_value). All gates default
CLOSED. Production signing additionally requires allow_production_signing (defense in depth -
the guard/service re-check)."""
import frappe
from frappe import _
from frappe.model.document import Document

_CLAMPS = {"request_timeout": (5, 180, 30), "polling_interval_s": (5, 300, 20),
           "max_poll_attempts": (1, 200, 30), "stale_after_hours": (1, 168, 24)}


class ECDigitalSignatureProviderSettings(Document):
    def validate(self):
        self.settings_key = "%s::%s" % (self.provider or "", self.environment or "")
        for f, (lo, hi, dflt) in _CLAMPS.items():
            v = self.get(f)
            try:
                v = int(v)
            except (TypeError, ValueError):
                v = dflt
            self.set(f, min(max(v, lo), hi))
        if self.environment == "Production" and not self.allow_production_signing:
            if self.allow_signing or self.allow_bulk_signing:
                frappe.throw(_("Production signing is disabled: allow_production_signing is OFF."))
