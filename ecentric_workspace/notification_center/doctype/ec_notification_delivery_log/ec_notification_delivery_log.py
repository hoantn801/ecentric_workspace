# Copyright (c) 2026, eCentric and contributors
"""EC Notification Delivery Log: per-(event, recipient, channel) audit + idempotency.
idempotency_key is UNIQUE so a re-run cannot create a duplicate delivery row. Admin-only
(System Manager) DocType — it is an audit trail, never user-facing."""
import frappe
from frappe.model.document import Document


class ECNotificationDeliveryLog(Document):
    pass
