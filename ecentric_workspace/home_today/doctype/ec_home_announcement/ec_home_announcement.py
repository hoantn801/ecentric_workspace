# Copyright (c) 2026, eCentric and contributors
"""EC Home Announcement - thong bao len popup "Hom nay o eCentric".

CRUD thuan (khong quy tac ngoai kiem ngay + xoa cache): hien thi / loc han nam o
home_today.domain.announcements. Luu / xoa -> xoa cache ngay de popup thay lien."""
import frappe
from frappe import _
from frappe.model.document import Document

from ecentric_workspace.home_today import repository


class ECHomeAnnouncement(Document):
    def validate(self):
        if self.end_date and self.start_date and str(self.end_date) < str(self.start_date):
            frappe.throw(_("Ngày kết thúc phải từ ngày bắt đầu trở đi."))

    def on_update(self):
        repository.cache_clear_today()

    def on_trash(self):
        repository.cache_clear_today()
