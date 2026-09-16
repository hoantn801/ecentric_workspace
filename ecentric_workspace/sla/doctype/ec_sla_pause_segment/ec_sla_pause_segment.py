# Copyright (c) 2026, eCentric and contributors
"""EC SLA Pause Segment - mot doan dong ho bi dung cua mot nghia vu."""
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import time_diff_in_seconds

from ecentric_workspace.sla.constants import ALL_PAUSE_REASONS


class ECSLAPauseSegment(Document):
    def validate(self):
        if self.reason not in ALL_PAUSE_REASONS:
            frappe.throw(_("reason '{0}' khong hop le.").format(self.reason))
        if not self.dedupe_key:
            frappe.throw(_("dedupe_key la bat buoc."))
        if self.to_dt:
            if self.to_dt < self.from_dt:
                frappe.throw(_("to_dt khong the truoc from_dt."))
            self.seconds = int(time_diff_in_seconds(self.to_dt, self.from_dt))
        else:
            # Doan chua ket thuc chua cong duoc gi. Cong tam theo "bay gio" se
            # lam han tu troi ra moi lan trang duoc mo - ti le doi theo nguoi xem.
            self.seconds = 0
