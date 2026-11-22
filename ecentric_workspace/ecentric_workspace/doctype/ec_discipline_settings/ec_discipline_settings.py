# Copyright (c) 2026, eCentric and contributors
"""EC Discipline Settings (Single). Repository doc qua frappe.get_cached_doc - Frappe tu xoa cache
khi luu. Chan so ngay bao truoc hop < 5 ngay lam viec (ND 145/2020 D70)."""
import frappe
from frappe import _
from frappe.model.document import Document

MIN_MEETING_NOTICE_DAYS = 5


class ECDisciplineSettings(Document):
    def validate(self):
        if self.meeting_notice_days and int(self.meeting_notice_days) < MIN_MEETING_NOTICE_DAYS:
            frappe.throw(_("Báo trước họp kỷ luật tối thiểu 5 ngày làm việc."))
