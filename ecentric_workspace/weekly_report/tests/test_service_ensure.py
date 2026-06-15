# Copyright (c) 2026, eCentric and contributors
"""Service-level tests for ensure_weekly_obligation.

These tests require WR1A custom fields on WTU to be installed (patch
p001_wtu_obligation_fields) AND a Department Reporting Window to exist for
the test department. The setUpClass installs a DRW row using the test
department; tearDownClass cleans up.

Tests that require a fully-working site (Employee/User/DRW present) are
marked with a clear docstring; if running before patch p001 has executed,
custom-field-dependent assertions will fail.
"""

from datetime import datetime

import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.weekly_report import service
from ecentric_workspace.weekly_report import week_calendar

TEST_DEPT = "All Departments"
TEST_USER = "wr1a_service_user@example.test"
TEST_EMP_ID = "WR1A-SVC-001"


def _make_user(email):
    if frappe.db.exists("User", email):
        return email
    u = frappe.get_doc({
        "doctype": "User",
        "email": email,
        "first_name": "WR1A Test",
        "send_welcome_email": 0,
        "enabled": 1,
    })
    u.insert(ignore_permissions=True)
    return email


def _make_employee(emp_id, user_email):
    existing = frappe.db.get_value("Employee", {"employee_number": emp_id}, "name")
    if existing:
        return existing
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
        "department": TEST_DEPT,
    })
    e.insert(ignore_permissions=True)
    return e.name


def _ensure_drw(dept):
    if frappe.db.exists("Department Reporting Window", dept):
        return
    drw = frappe.get_doc({
        "doctype": "Department Reporting Window",
        "department": dept,
        "week_start_day": "Monday",
        "week_end_day": "Friday",
        "deadline_day": "Friday",
        "deadline_time": "18:00:00",
        "deadline_in_next_week": 0,
        "enabled": 1,
    })
    drw.insert(ignore_permissions=True)


class TestEnsureObligation(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = _make_user(TEST_USER)
        cls.emp = _make_employee(TEST_EMP_ID, cls.user)
        _ensure_drw(TEST_DEPT)
        cls.schedule = {
            "name": "WRS-TEST-EMP-001",
            "employee": cls.emp,
            "user": cls.user,
            "reporting_department": TEST_DEPT,
            "effective_from": "2026-01-01",
            "effective_to": None,
            "last_generated_week": None,
        }
        cls.week = week_calendar.compute_week_for(datetime(2026, 6, 15, 10, 0, 0))

    def _cleanup_wtu(self):
        rows = frappe.get_all(
            "Weekly Team Update",
            filters={"submitter": self.user, "week_label": self.week["week_label"]},
            pluck="name",
        )
        for n in rows:
            for t in frappe.get_all("ToDo",
                    filters={"reference_type": "Weekly Team Update", "reference_name": n},
                    pluck="name"):
                frappe.delete_doc("ToDo", t, ignore_permissions=True, force=True)
            frappe.delete_doc("Weekly Team Update", n, ignore_permissions=True, force=True)

    def setUp(self):
        self._cleanup_wtu()

    def tearDown(self):
        self._cleanup_wtu()

    def test_creates_draft_when_none(self):
        out = service.ensure_weekly_obligation(self.schedule, self.week,
            now=datetime(2026, 6, 15, 10, 0, 0))
        self.assertEqual(out, "created")
        wtus = frappe.get_all(
            "Weekly Team Update",
            filters={"submitter": self.user, "week_label": self.week["week_label"]},
            fields=["name", "status", "generated_obligation", "obligation_key"],
        )
        self.assertEqual(len(wtus), 1)
        self.assertEqual(wtus[0].status, "Draft")
        self.assertEqual(wtus[0].generated_obligation, 1)
        self.assertEqual(
            wtus[0].obligation_key,
            self.emp + "::" + self.week["week_label"],
        )

    def test_idempotent_second_call(self):
        out1 = service.ensure_weekly_obligation(self.schedule, self.week)
        out2 = service.ensure_weekly_obligation(self.schedule, self.week)
        self.assertEqual(out1, "created")
        self.assertEqual(out2, "reused")
        wtus = frappe.get_all("Weekly Team Update",
            filters={"submitter": self.user, "week_label": self.week["week_label"]})
        self.assertEqual(len(wtus), 1)
        todos = frappe.get_all("ToDo",
            filters={"reference_type": "Weekly Team Update",
                     "reference_name": wtus[0].name, "status": "Open"})
        self.assertEqual(len(todos), 1)

    def test_legacy_submitted_skipped(self):
        # Create a Submitted WTU as if user already submitted before WR1A.
        legacy = frappe.get_doc({
            "doctype": "Weekly Team Update",
            "submitter": self.user,
            "employee": self.emp,
            "department": TEST_DEPT,
            "week_label": self.week["week_label"],
            "week_start_date": self.week["week_start_date"],
            "week_end_date": self.week["week_end_date"],
            "status": "Submitted",
        }).insert(ignore_permissions=True)
        out = service.ensure_weekly_obligation(self.schedule, self.week)
        self.assertEqual(out, "skipped")

    def test_legacy_draft_adopted(self):
        legacy = frappe.get_doc({
            "doctype": "Weekly Team Update",
            "submitter": self.user,
            "employee": self.emp,
            "department": TEST_DEPT,
            "week_label": self.week["week_label"],
            "week_start_date": self.week["week_start_date"],
            "week_end_date": self.week["week_end_date"],
            "status": "Draft",
        }).insert(ignore_permissions=True)
        out = service.ensure_weekly_obligation(self.schedule, self.week)
        self.assertEqual(out, "adopted")
        legacy.reload()
        self.assertEqual(legacy.generated_obligation, 1)
        self.assertEqual(
            legacy.obligation_key,
            self.emp + "::" + self.week["week_label"],
        )

    def test_missing_drw_raises(self):
        bad_schedule = dict(self.schedule)
        bad_schedule["reporting_department"] = "NonExistent Department XYZ"
        with self.assertRaises(week_calendar.MissingReportingWindowError):
            service.ensure_weekly_obligation(bad_schedule, self.week)
