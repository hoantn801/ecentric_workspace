# Copyright (c) 2026, eCentric and contributors
"""EC Notification Preference: one record per user (autoname field:user). Users may
read/write ONLY their own record (if_owner); System Manager administers. The API layer
(notification_center.api) is the gateway and always scopes to frappe.session.user."""
import frappe
from frappe import _
from frappe.model.document import Document

SEVERITIES = ("info", "action_required", "urgent")


class ECNotificationPreference(Document):
    def validate(self):
        if self.minimum_severity and self.minimum_severity not in SEVERITIES:
            frappe.throw(_("Invalid minimum_severity"))
        # quiet hours may legitimately cross midnight (start > end); no validation needed.
