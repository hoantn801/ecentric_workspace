# Copyright (c) 2026, eCentric and contributors
"""EC Meeting Room - phòng họp văn phòng (05/11/2026).

One row per room = one Microsoft 365 room mailbox (`email`). The calendar itself lives in
Exchange (source of truth, shared with Teams/Outlook); ERP only keeps the list + display data.
Read/booked through ecentric_workspace.pm.api.rooms."""
import frappe
from frappe import _
from frappe.model.document import Document


class ECMeetingRoom(Document):
    def validate(self):
        self.room_code = (self.room_code or "").strip()
        self.room_title = (self.room_title or "").strip()
        self.email = (self.email or "").strip().lower()
        if not self.email or "@" not in self.email:
            frappe.throw(_("Email phòng không hợp lệ."))

    def on_update(self):
        from ecentric_workspace.pm.api import rooms
        rooms.clear_cache()
