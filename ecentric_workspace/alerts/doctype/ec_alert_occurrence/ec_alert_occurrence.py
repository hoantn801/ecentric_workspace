# Copyright (c) 2026, eCentric
# Alert Center Phase G1.1 - per-order-line price-violation EVIDENCE.
# Immutable, append-only: one row per (external_order_id, external_line_id,
# rule_code) via the UNIQUE dedupe_key. Created by services.alert_engine; the
# Case (EC Alert) holds the rollup KAM works on. SM-only DocPerm; all business
# access is through whitelisted services (api_alerts).

from frappe.model.document import Document


class ECAlertOccurrence(Document):
    pass
