# Copyright (c) 2026, eCentric and contributors
"""Tests for the run_weekly_report_pilot whitelisted endpoint."""

from datetime import datetime

import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.weekly_report import api as wr_api
from ecentric_workspace.weekly_report import week_calendar

TEST_DEPT = "All Departments"
TEST_USER = "wr_hotfix_pilot_user@example.test"
TEST_EMP_ID = "WR-HOTFIX-PILOT-001"
NON_ADMIN_USER = "wr_hotfix_pilot_normal@example.test"


def _make_user(email, roles=None):
    if frappe.db.exists("User", email):
        frappe.db.set_value("User", email, "enabled", 1)
        if roles is not None:
            doc = frappe.get_doc("User", email)
            existing_roles = set(r.role for r in doc.roles)
            for r in roles:
                if r not in existing_roles:
                    doc.append("roles", {"role": r})
            doc.save(ignore_permissions=True)
        return email
    doc = frappe.get_doc({
        "doctype": "User", "email": email,
        "first_name": "Pilot Test",
        "send_welcome_email": 0, "enabled": 1,
    })
    if roles:
        for r in roles:
            doc.append("roles", {"role": r})
    doc.insert(ignore_permissions=True)
    return email


def _make_employee(emp_id, user_email):
    existing = frappe.db.get_value("Employee", {"employee_number": emp_id}, "name")
    if existing:
        frappe.db.set_value("Employee", existing, {
            "status": "Active", "user_id": user_email, "department": TEST_DEPT,
        })
        return existing
    e = frappe.get_doc({
        "doctype": "Employee",
        "employee_number": emp_id,
        "first_name": "Pilot", "last_name": emp_id,
        "gender": "Male", "date_of_birth": "1990-01-01",
        "date_of_joining": "2026-01-01", "status": "Active",
        "user_id": user_email, "department": TEST_DEPT,
    })
    e.insert(ignore_permissions=True)
    return e.name


def _ensure_drw(dept):
    if frappe.db.exists("Department Reporting Window", dept):
        frappe.db.set_value("Department Reporting Window", dept, "enabled", 1)
        return
    frappe.get_doc({
        "doctype": "Department Reporting Window",
        "department": dept,
        "week_start_day": "Monday", "week_end_day": "Friday",
        "deadline_day": "Friday", "deadline_time": "18:00:00",
        "deadline_in_next_week": 0, "enabled": 1,
    }).insert(ignore_permissions=True)


class TestPilotApi(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = _make_user(TEST_USER)
        cls.normal_user = _make_user(NON_ADMIN_USER)
        cls.emp = _make_employee(TEST_EMP_ID, cls.user)
        _ensure_drw(TEST_DEPT)
        cls.week = week_calendar.compute_week_for(datetime(2026, 6, 15, 10, 0, 0))

    def _cleanup(self):
        for n in frappe.get_all("Weekly Team Update",
                filters={"submitter": self.user, "week_label": self.week["week_label"]},
                pluck="name"):
            for t in frappe.get_all("ToDo",
                    filters={"reference_type": "Weekly Team Update",
                             "reference_name": n}, pluck="name"):
                frappe.delete_doc("ToDo", t, ignore_permissions=True, force=True)
            frappe.delete_doc("Weekly Team Update", n,
                ignore_permissions=True, force=True)

    def setUp(self):
        self._cleanup()
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")
        self._cleanup()

    # 1. Guest blocked
    def test_guest_blocked(self):
        frappe.set_user("Guest")
        try:
            with self.assertRaises(frappe.PermissionError):
                wr_api.run_weekly_report_pilot(employee=self.emp)
        finally:
            frappe.set_user("Administrator")

    # 2. Non-System Manager blocked
    def test_non_system_manager_blocked(self):
        frappe.set_user(self.normal_user)
        try:
            with self.assertRaises(frappe.PermissionError):
                wr_api.run_weekly_report_pilot(employee=self.emp)
        finally:
            frappe.set_user("Administrator")

    # 3. Employee not found
    def test_employee_not_found_blocked(self):
        # Administrator has System Manager implicitly.
        with self.assertRaises(frappe.ValidationError):
            wr_api.run_weekly_report_pilot(employee="NONEXISTENT-EMP-ZZ-9999")

    # 4. System Manager runs exactly one Employee
    def test_system_manager_runs_one_employee(self):
        stats = wr_api.run_weekly_report_pilot(employee=self.emp)
        self.assertFalse(stats.get("disabled", False))
        self.assertEqual(stats["processed"], 1)
        self.assertEqual(stats["created"], 1)
        wtus = frappe.get_all("Weekly Team Update",
            filters={"submitter": self.user,
                     "week_label": self.week["week_label"]})
        self.assertEqual(len(wtus), 1)

    # 5. Cannot run full batch via pilot endpoint
    def test_cannot_call_full_batch(self):
        # 5a: list/collection rejected
        with self.assertRaises(frappe.ValidationError):
            wr_api.run_weekly_report_pilot(employee=[self.emp])
        with self.assertRaises(frappe.ValidationError):
            wr_api.run_weekly_report_pilot(employee=(self.emp,))
        with self.assertRaises(frappe.ValidationError):
            wr_api.run_weekly_report_pilot(employee={"name": self.emp})
        # 5b: empty/None rejected
        with self.assertRaises(frappe.ValidationError):
            wr_api.run_weekly_report_pilot(employee=None)
        with self.assertRaises(frappe.ValidationError):
            wr_api.run_weekly_report_pilot(employee="")
        with self.assertRaises(frappe.ValidationError):
            wr_api.run_weekly_report_pilot(employee="   ")
