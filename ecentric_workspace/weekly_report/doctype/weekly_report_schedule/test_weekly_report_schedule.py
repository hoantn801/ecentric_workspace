# Copyright (c) 2026, eCentric and contributors
# Tests for Weekly Report Schedule controller.
"""Controller tests for Weekly Report Schedule.

Covered:
1. schedule_key auto-set to employee on validate.
2. user resolved from Employee.user_id on validate.
3. Missing user_id on Employee -> validate raises.
4. Employee swap blocked after create.
"""

import frappe
from frappe.tests.utils import FrappeTestCase


def _make_user(email):
    if frappe.db.exists("User", email):
        return email
    u = frappe.get_doc({
        "doctype": "User",
        "email": email,
        "first_name": email.split("@")[0],
        "send_welcome_email": 0,
        "enabled": 1,
    })
    u.insert(ignore_permissions=True)
    return email


def _make_employee(emp_id, user_email=None):
    if frappe.db.exists("Employee", {"employee_number": emp_id}):
        return frappe.db.get_value("Employee", {"employee_number": emp_id}, "name")
    e = frappe.get_doc({
        "doctype": "Employee",
        "employee_number": emp_id,
        "first_name": "Test",
        "last_name": emp_id,
        "gender": "Male",
        "date_of_birth": "1990-01-01",
        "date_of_joining": "2026-01-01",
        "status": "Active",
        "user_id": user_email,
    })
    e.insert(ignore_permissions=True)
    return e.name


class TestWeeklyReportSchedule(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user_a = _make_user("wr1a_user_a@example.test")
        cls.user_b = _make_user("wr1a_user_b@example.test")
        cls.emp_with_user = _make_employee("WR1A-TEST-001", cls.user_a)
        cls.emp_without_user = _make_employee("WR1A-TEST-002", None)
        cls.dept = "All Departments"

    def test_schedule_key_set_to_employee(self):
        s = frappe.get_doc({
            "doctype": "Weekly Report Schedule",
            "employee": self.emp_with_user,
            "reporting_department": self.dept,
            "effective_from": "2026-06-01",
        })
        s.insert(ignore_permissions=True)
        self.assertEqual(s.schedule_key, self.emp_with_user)
        s.delete(ignore_permissions=True)

    def test_user_resolved_from_employee(self):
        s = frappe.get_doc({
            "doctype": "Weekly Report Schedule",
            "employee": self.emp_with_user,
            "reporting_department": self.dept,
            "effective_from": "2026-06-01",
        })
        s.insert(ignore_permissions=True)
        self.assertEqual(s.user, self.user_a)
        s.delete(ignore_permissions=True)

    def test_missing_user_id_raises(self):
        s = frappe.get_doc({
            "doctype": "Weekly Report Schedule",
            "employee": self.emp_without_user,
            "reporting_department": self.dept,
            "effective_from": "2026-06-01",
        })
        with self.assertRaises(frappe.ValidationError):
            s.insert(ignore_permissions=True)

    def test_employee_swap_blocked_after_create(self):
        s = frappe.get_doc({
            "doctype": "Weekly Report Schedule",
            "employee": self.emp_with_user,
            "reporting_department": self.dept,
            "effective_from": "2026-06-01",
        })
        s.insert(ignore_permissions=True)
        # Try to swap employee
        emp_b = _make_employee("WR1A-TEST-003", self.user_b)
        s.employee = emp_b
        with self.assertRaises(frappe.ValidationError):
            s.save(ignore_permissions=True)
        s.reload()
        s.delete(ignore_permissions=True)

    def test_duplicate_schedule_per_employee_blocked(self):
        """schedule_key=employee with DB unique=1 blocks second Schedule for same Employee."""
        s1 = frappe.get_doc({
            "doctype": "Weekly Report Schedule",
            "employee": self.emp_with_user,
            "reporting_department": self.dept,
            "effective_from": "2026-06-01",
        })
        s1.insert(ignore_permissions=True)
        try:
            s2 = frappe.get_doc({
                "doctype": "Weekly Report Schedule",
                "employee": self.emp_with_user,
                "reporting_department": self.dept,
                "effective_from": "2026-06-01",
            })
            # DB unique constraint on schedule_key (= employee) raises.
            with self.assertRaises((frappe.UniqueValidationError, frappe.DuplicateEntryError)):
                s2.insert(ignore_permissions=True)
        finally:
            s1.delete(ignore_permissions=True)
