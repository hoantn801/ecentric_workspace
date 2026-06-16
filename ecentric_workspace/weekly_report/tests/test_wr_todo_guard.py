# Copyright (c) 2026, eCentric and contributors
"""Guard tests for validate_weekly_report_todo (Employee-driven setUp)."""

from datetime import datetime

import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.weekly_report import service
from ecentric_workspace.weekly_report import week_calendar

TEST_DEPT = "All Departments"
TEST_USER = "wr_hotfix_guard_user@example.test"
TEST_EMP_ID = "WR-HOTFIX-GUARD-001"


def _make_user(email):
    if frappe.db.exists("User", email):
        frappe.db.set_value("User", email, "enabled", 1)
        return email
    frappe.get_doc({
        "doctype": "User", "email": email,
        "first_name": "Guard Test", "send_welcome_email": 0, "enabled": 1,
    }).insert(ignore_permissions=True)
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
        "first_name": "Guard", "last_name": emp_id,
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


class TestWrTodoGuard(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = _make_user(TEST_USER)
        cls.emp = _make_employee(TEST_EMP_ID, cls.user)
        _ensure_drw(TEST_DEPT)
        cls.week = week_calendar.compute_week_for(datetime(2026, 6, 15, 10, 0, 0))

    def _cleanup(self):
        for n in frappe.get_all("Weekly Team Update",
                filters={"submitter": self.user, "week_label": self.week["week_label"]},
                pluck="name"):
            for t in frappe.get_all("ToDo",
                    filters={"reference_type": "Weekly Team Update", "reference_name": n},
                    pluck="name"):
                frappe.delete_doc("ToDo", t, ignore_permissions=True, force=True)
            frappe.delete_doc("Weekly Team Update", n, ignore_permissions=True, force=True)

    def setUp(self):
        self._cleanup()

    def tearDown(self):
        self._cleanup()

    def _get_obligation_todo(self, wtu_name):
        rows = frappe.get_all("ToDo",
            filters={"reference_type": "Weekly Team Update",
                     "reference_name": wtu_name, "status": "Open"},
            pluck="name")
        return rows[0] if rows else None

    def test_manual_close_blocked_while_draft(self):
        service.ensure_weekly_obligation(self.emp, self.week)
        wtu = frappe.db.get_value("Weekly Team Update",
            {"submitter": self.user, "week_label": self.week["week_label"]}, "name")
        td = frappe.get_doc("ToDo", self._get_obligation_todo(wtu))
        td.status = "Closed"
        with self.assertRaises((frappe.PermissionError, frappe.ValidationError)):
            td.save(ignore_permissions=True)

    def test_manual_cancel_blocked_while_draft(self):
        service.ensure_weekly_obligation(self.emp, self.week)
        wtu = frappe.db.get_value("Weekly Team Update",
            {"submitter": self.user, "week_label": self.week["week_label"]}, "name")
        td = frappe.get_doc("ToDo", self._get_obligation_todo(wtu))
        td.status = "Cancelled"
        with self.assertRaises((frappe.PermissionError, frappe.ValidationError)):
            td.save(ignore_permissions=True)

    def test_service_close_after_submit_passes(self):
        service.ensure_weekly_obligation(self.emp, self.week)
        wtu = frappe.db.get_value("Weekly Team Update",
            {"submitter": self.user, "week_label": self.week["week_label"]}, "name")
        frappe.db.set_value("Weekly Team Update", wtu, "status", "Submitted")
        service.close_weekly_obligation(wtu)
        for t in frappe.get_all("ToDo",
                filters={"reference_type": "Weekly Team Update",
                         "reference_name": wtu}, fields=["status"]):
            self.assertEqual(t.status, "Closed")

    def test_legacy_wtu_not_blocked(self):
        legacy = frappe.get_doc({
            "doctype": "Weekly Team Update",
            "submitter": self.user, "employee": self.emp,
            "department": TEST_DEPT,
            "week_label": self.week["week_label"],
            "week_start_date": self.week["week_start_date"],
            "week_end_date": self.week["week_end_date"],
            "status": "Draft",
        }).insert(ignore_permissions=True)
        td = frappe.get_doc({
            "doctype": "ToDo",
            "allocated_to": self.user,
            "reference_type": "Weekly Team Update",
            "reference_name": legacy.name,
            "status": "Open",
            "description": "Legacy todo",
        })
        td.insert(ignore_permissions=True)
        td.status = "Closed"
        td.save(ignore_permissions=True)
        td.reload()
        self.assertEqual(td.status, "Closed")

    def test_approval_todo_not_blocked(self):
        td = frappe.get_doc({
            "doctype": "ToDo",
            "allocated_to": self.user,
            "reference_type": "User",
            "reference_name": self.user,
            "status": "Open",
            "description": "Foreign reference",
        })
        td.insert(ignore_permissions=True)
        td.status = "Closed"
        td.save(ignore_permissions=True)
        td.reload()
        self.assertEqual(td.status, "Closed")
