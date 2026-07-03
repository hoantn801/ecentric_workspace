# Copyright (c) 2026, eCentric and contributors
"""EC Approval Business Calendar - reusable working-hours calendar."""
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_time


class ECApprovalBusinessCalendar(Document):
    def validate(self):
        if not self.is_new():
            before = self.get_doc_before_save()
            if before and before.calendar_code and before.calendar_code != self.calendar_code:
                frappe.throw(_("calendar_code is immutable."))
        if self.active and not self.working_periods:
            frappe.throw(_("An active calendar must have at least one working period."))
        by_day = {}
        for p in (self.working_periods or []):
            st, et = get_time(p.start_time), get_time(p.end_time)
            if st >= et:
                frappe.throw(_("{0}: start_time must be earlier than end_time.").format(p.weekday))
            by_day.setdefault(p.weekday, []).append((st, et))
        for day, spans in by_day.items():
            spans.sort()
            for i in range(1, len(spans)):
                if spans[i] == spans[i - 1]:
                    frappe.throw(_("{0}: duplicate working period.").format(day))
                if spans[i][0] < spans[i - 1][1]:
                    frappe.throw(_("{0}: overlapping working periods.").format(day))
        # deterministic ordering
        order = {d: i for i, d in enumerate(
            ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])}
        self.working_periods.sort(key=lambda p: (order.get(p.weekday, 9), get_time(p.start_time)))
        for i, p in enumerate(self.working_periods):
            p.idx = i + 1
            p.sequence = i
