# Copyright (c) 2026, eCentric and contributors
# For license information, please see license.txt
"""Weekly Report Schedule controller.

One row per Employee. The schedule_key field doubles as a DB-level uniqueness
constraint on `employee` (we set schedule_key = employee in validate; the
unique=1 on schedule_key prevents duplicate Schedules for the same Employee).

Department changes are allowed; they only affect obligations generated AFTER
the change. Employee changes are blocked after the row is created.
"""

import frappe
from frappe import _
from frappe.model.document import Document


class WeeklyReportSchedule(Document):
    def validate(self):
        if not self.employee:
            frappe.throw(_("Employee is required."))

        # Block Employee swap after create. reporting_department remains editable.
        if not self.is_new() and self.has_value_changed("employee"):
            frappe.throw(_("Cannot change Employee on an existing Weekly Report Schedule."))

        # Resolve user from Employee.user_id (server-side; do NOT rely on fetch_from).
        user_id = frappe.db.get_value("Employee", self.employee, "user_id")
        if not user_id:
            frappe.throw(
                _("Employee {0} has no linked User (user_id). Link a User to the Employee before creating a Schedule.").format(
                    self.employee
                )
            )
        self.user = user_id

        # schedule_key = employee (DB unique enforces 1 Schedule per Employee).
        self.schedule_key = self.employee

        # Effective range sanity.
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            frappe.throw(_("Effective To must be >= Effective From."))
