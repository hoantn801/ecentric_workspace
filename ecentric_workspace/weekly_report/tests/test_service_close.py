# Copyright (c) 2026, eCentric and contributors
"""Tests for close_weekly_obligation lifecycle.

Verifies:
  1. open ToDo gets removed from _assign, status -> Closed
  2. no open ToDo -> no-op
  3. close error -> raised, not swallowed
"""

from datetime import datetime

import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.weekly_report import service
from ecentric_workspace.weekly_report import week_calendar

TEST_DEPT = "All Departments"
TEST_USER = "wr1a_close_user@example.test"
TEST_EMP_ID = "WR1A-CLOSE-001"


def _make_user(email):
    if frappe.db.exists("User", email):
        return email
    frappe.get_doc({
        "doctype": "User", "email": email,
        "first_name": "Close Test", "send_welcome_email": 0, "enabled": 1,
    }).insert(ignore_permissions=True)
    return email


def _make_employee(emp_id, user_email):
    existing = frappe.db.get_value("Employee", {"employee_number": emp_id}, "name")
    if existing:
        return existing
    e = frappe.get_doc({
        "doctype": "Employee",
        "employee_number": emp_id,
        "first_name": "Close", "last_name": emp_id,
        "gender": "Male", "date_of_birth": "1990-01-01",
        "date_of_joining": "2026-01-01", "status": "Active",
        "user_id": user_email, "department": TEST_DEPT,
    })
    e.insert(ignore_permissions=True)
    return e.name


def _ensure_drw(dept):
    if frappe.db.exists("Department Reporting Window", dept):
        return
    frappe.get_doc({
        "doctype": "Department Reporting Window",
        "department": dept,
        "week_start_day": "Monday", "week_end_day": "Friday",
        "deadline_day": "Friday", "deadline_time": "18:00:00",
        "deadline_in_next_week": 0, "enabled": 1,
    }).insert(ignore_permissions=True)


class TestCloseObligation(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = _make_user(TEST_USER)
        cls.emp = _make_employee(TEST_EMP_ID, cls.user)
        _ensure_drw(TEST_DEPT)
        cls.week = week_calendar.compute_week_for(datetime(2026, 6, 15, 10, 0, 0))
        cls.schedule = {
            "name": "WRS-CLOSE-EMP-001",
            "employee": cls.emp,
            "user": cls.user,
            "reporting_department": TEST_DEPT,
            "effective_from": "2026-01-01",
            "effective_to": None,
            "last_generated_week": None,
        }

    def _cleanup(self):
        rows = frappe.get_all("Weekly Team Update",
            filters={"submitter": self.user, "week_label": self.week["week_label"]},
            pluck="name")
        for n in rows:
            for t in frappe.get_all("ToDo",
                    filters={"reference_type": "Weekly Team Update", "reference_name": n},
                    pluck="name"):
                frappe.delete_doc("ToDo", t, ignore_permissions=True, force=True)
            frappe.delete_doc("Weekly Team Update", n, ignore_permissions=True, force=True)

    def setUp(self):
        self._cleanup()

    def tearDown(self):
        self._cleanup()

    def test_close_marks_open_todo_closed(self):
        service.ensure_weekly_obligation(self.schedule, self.week)
        wtu = frappe.db.get_value("Weekly Team Update",
            {"submitter": self.user, "week_label": self.week["week_label"]}, "name")
        # WTU has to be Submitted for the guard to allow the close path.
        frappe.db.set_value("Weekly Team Update", wtu, "status", "Submitted")
        service.close_weekly_obligation(wtu)
        todos = frappe.get_all("ToDo",
            filters={"reference_type": "Weekly Team Update", "reference_name": wtu},
            fields=["name", "status"])
        for t in todos:
            self.assertEqual(t.status, "Closed")

    def test_close_idempotent_when_no_open_todo(self):
        # Make a WTU with no ToDo; close should be a clean no-op.
        wtu = frappe.get_doc({
            "doctype": "Weekly Team Update",
            "submitter": self.user, "employee": self.emp,
            "department": TEST_DEPT,
            "week_label": self.week["week_label"],
            "week_start_date": self.week["week_start_date"],
            "week_end_date": self.week["week_end_date"],
            "status": "Submitted",
        }).insert(ignore_permissions=True)
        try:
            service.close_weekly_obligation(wtu.name)
        except Exception as e:
            self.fail("close should be no-op without raising: " + str(e))

    def test_close_error_raises_not_swallowed(self):
        """If assign_to.remove fails mid-close, exception MUST bubble up.

        We do not enter half-state (WTU=Submitted + ToDo Open) silently. The
        service raises so the surrounding save transaction rolls back.
        """
        service.ensure_weekly_obligation(self.schedule, self.week)
        wtu = frappe.db.get_value("Weekly Team Update",
            {"submitter": self.user, "week_label": self.week["week_label"]}, "name")
        frappe.db.set_value("Weekly Team Update", wtu, "status", "Submitted")
        # Monkey-patch native remove to raise.
        import frappe.desk.form.assign_to as _at
        orig = _at.remove
        def _boom(*a, **kw):
            raise RuntimeError("simulated assign_to.remove failure")
        _at.remove = _boom
        try:
            with self.assertRaises(RuntimeError):
                service.close_weekly_obligation(wtu)
        finally:
            _at.remove = orig

    # ===== WR1A-V FIX 3: missing allocated_to MUST raise ==================

    def test_missing_allocated_to_raises(self):
        """Open ToDo without allocated_to cannot be closed via assign_to API;
        service.close_weekly_obligation must RAISE (not silent skip)."""
        wtu = frappe.get_doc({
            "doctype": "Weekly Team Update",
            "submitter": self.user, "employee": self.emp,
            "department": TEST_DEPT,
            "week_label": self.week["week_label"],
            "week_start_date": self.week["week_start_date"],
            "week_end_date": self.week["week_end_date"],
            "status": "Submitted",
            "generated_obligation": 1,
            "obligation_key": self.emp + "::" + self.week["week_label"],
        }).insert(ignore_permissions=True)
        # Create a ToDo with NO allocated_to.
        td = frappe.get_doc({
            "doctype": "ToDo",
            "reference_type": "Weekly Team Update",
            "reference_name": wtu.name,
            "status": "Open",
            "description": "broken: no allocated_to",
        })
        td.insert(ignore_permissions=True)
        with self.assertRaises(frappe.ValidationError):
            service.close_weekly_obligation(wtu.name)
