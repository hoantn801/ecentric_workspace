# Copyright (c) 2026, eCentric and contributors
"""EC Timesheet Close - mot dong / nhan vien / ky cong. Logic o hr/timesheet_close."""
from frappe.model.document import Document


class ECTimesheetClose(Document):
    def autoname(self):
        # Khoa tu nhien: moi nhan vien chi co MOT dong cho moi ky -> chay lai bao
        # nhieu lan cung khong sinh ban sao.
        self.name = "%s-%s" % (self.period_month, self.employee)
