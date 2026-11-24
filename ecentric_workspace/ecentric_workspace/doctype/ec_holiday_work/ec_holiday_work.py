# Copyright (c) 2026, eCentric and contributors
"""EC Holiday Work - danh sach di lam ngay nghi. Logic o hr/holiday_work/service.py."""
import frappe
from frappe.model.document import Document


class ECHolidayWork(Document):
    def validate(self):
        from ecentric_workspace.hr.holiday_work import service
        service.validate(self)

    def on_update(self):
        if getattr(self.flags, "skip_holiday_work_apply", False):
            return
        from ecentric_workspace.hr.holiday_work import service
        try:
            service.apply(self.name)
        except Exception:
            frappe.log_error(title="EC Holiday Work apply %s" % self.name,
                             message=frappe.get_traceback())
