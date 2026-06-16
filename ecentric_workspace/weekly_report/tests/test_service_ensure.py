# Copyright (c) 2026, eCentric and contributors
"""Hotfix service ensure_weekly_obligation tests (Employee-driven).

Covers the 12 mandatory cases:
  1. Active Employee + enabled User + enabled DRW -> create 1 WTU + 1 ToDo.
  2. Re-run -> no duplicate.
  3. Employee inactive -> skip.
  4. User disabled -> skip.
  5. Employee missing user_id -> skip.
  6. Employee missing department -> skip.
  7. Department missing DRW -> MissingReportingWindowError raised.
  8. DRW disabled -> MissingReportingWindowError raised.
  9. Employee changes department -> next week uses new dept + deadline.
 10. Submitted/Reviewed WTU -> no ToDo recreation (terminal-state).
"""

from datetime import datetime

import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.weekly_report import service
from ecentric_workspace.weekly_report import week_calendar

TEST_DEPT_A = "All Departments"
TEST_DEPT_B = "WR Hotfix Dept B"
TEST_USER = "wr_hotfix_user@example.test"
TEST_EMP_ID = "WR-HOTFIX-EMP-001"


def _make_user(email):
    if frappe.db.exists("User", email):
        return email
    frappe.get_doc({
        "doctype": "User", "email": email,
        "first_name": "WR Hotfix Test", "send_welcome_email": 0, "enabled": 1,
    }).insert(ignore_permissions=True)
    return email


def _make_employee(emp_id, user_email, dept):
    existing = frappe.db.get_value("Employee", {"employee_number": emp_id}, "name")
    if existing:
        return existing
    e = frappe.get_doc({
        "doctype": "Employee",
        "employee_number": emp_id,
        "first_name": "Test", "last_name": emp_id,
        "gender": "Male", "date_of_birth": "1990-01-01",
        "date_of_joining": "2026-01-01", "status": "Active",
        "user_id": user_email, "department": dept,
    })
    e.insert(ignore_permissions=True)
    return e.name


def _ensure_dept(dept):
    if frappe.db.exists("Department", dept):
        return
    frappe.get_doc({
        "doctype": "Department", "department_name": dept,
    }).insert(ignore_permissions=True)


def _ensure_drw(dept, enabled=1, deadline_day="Friday",
                deadline_time="18:00:00", deadline_in_next_week=0):
    if frappe.db.exists("Department Reporting Window", dept):
        frappe.db.set_value("Department Reporting Window", dept, {
            "enabled": enabled, "deadline_day": deadline_day,
            "deadline_time": deadline_time,
            "deadline_in_next_week": deadline_in_next_week,
        })
        return
    frappe.get_doc({
        "doctype": "Department Reporting Window",
        "department": dept,
        "week_start_day": "Monday", "week_end_day": "Friday",
        "deadline_day": deadline_day, "deadline_time": deadline_time,
        "deadline_in_next_week": deadline_in_next_week, "enabled": enabled,
    }).insert(ignore_permissions=True)


class TestEnsureObligation(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = _make_user(TEST_USER)
        _ensure_dept(TEST_DEPT_A)
        _ensure_dept(TEST_DEPT_B)
        cls.emp = _make_employee(TEST_EMP_ID, cls.user, TEST_DEPT_A)
        _ensure_drw(TEST_DEPT_A)
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
        # Reset Employee to known-good baseline before each test.
        frappe.db.set_value("Employee", self.emp, {
            "status": "Active", "user_id": self.user, "department": TEST_DEPT_A,
        })
        frappe.db.set_value("User", self.user, "enabled", 1)
        _ensure_drw(TEST_DEPT_A, enabled=1)
        self._cleanup_wtu()

    def tearDown(self):
        self._cleanup_wtu()

    # ---- 1. happy path ---------------------------------------------------
    def test_active_employee_creates_wtu_and_todo(self):
        out = service.ensure_weekly_obligation(self.emp, self.week,
            now=datetime(2026, 6, 15, 10, 0, 0))
        self.assertEqual(out, "created")
        wtus = frappe.get_all("Weekly Team Update",
            filters={"submitter": self.user, "week_label": self.week["week_label"]},
            fields=["name", "status", "generated_obligation", "obligation_key", "department"])
        self.assertEqual(len(wtus), 1)
        self.assertEqual(wtus[0].status, "Draft")
        self.assertEqual(wtus[0].generated_obligation, 1)
        self.assertEqual(wtus[0].obligation_key, self.emp + "::" + self.week["week_label"])
        self.assertEqual(wtus[0].department, TEST_DEPT_A)
        todos = frappe.get_all("ToDo",
            filters={"reference_type": "Weekly Team Update",
                     "reference_name": wtus[0].name, "status": "Open"})
        self.assertEqual(len(todos), 1)

    # ---- 2. idempotency --------------------------------------------------
    def test_idempotent_no_duplicate(self):
        o1 = service.ensure_weekly_obligation(self.emp, self.week)
        o2 = service.ensure_weekly_obligation(self.emp, self.week)
        self.assertEqual(o1, "created")
        self.assertEqual(o2, "reused")
        wtus = frappe.get_all("Weekly Team Update",
            filters={"submitter": self.user, "week_label": self.week["week_label"]})
        self.assertEqual(len(wtus), 1)
        todos = frappe.get_all("ToDo",
            filters={"reference_type": "Weekly Team Update",
                     "reference_name": wtus[0].name, "status": "Open"})
        self.assertEqual(len(todos), 1)

    # ---- 3. employee inactive -------------------------------------------
    def test_inactive_employee_skipped(self):
        frappe.db.set_value("Employee", self.emp, "status", "Inactive")
        out = service.ensure_weekly_obligation(self.emp, self.week)
        self.assertEqual(out, "skipped")
        self.assertEqual(len(frappe.get_all("Weekly Team Update",
            filters={"submitter": self.user, "week_label": self.week["week_label"]})), 0)

    # ---- 4. user disabled -----------------------------------------------
    def test_disabled_user_skipped(self):
        frappe.db.set_value("User", self.user, "enabled", 0)
        out = service.ensure_weekly_obligation(self.emp, self.week)
        self.assertEqual(out, "skipped")

    # ---- 5. employee missing user_id ------------------------------------
    def test_missing_user_id_skipped(self):
        frappe.db.set_value("Employee", self.emp, "user_id", None)
        out = service.ensure_weekly_obligation(self.emp, self.week)
        self.assertEqual(out, "skipped")

    # ---- 6. employee missing department ---------------------------------
    def test_missing_department_skipped(self):
        frappe.db.set_value("Employee", self.emp, "department", None)
        out = service.ensure_weekly_obligation(self.emp, self.week)
        self.assertEqual(out, "skipped")

    # ---- 7. DRW missing for department ----------------------------------
    def test_missing_drw_raises(self):
        # Point Employee at a department with no DRW.
        bogus = "Nonexistent Dept WR-HOTFIX-XYZ"
        _ensure_dept(bogus)
        if frappe.db.exists("Department Reporting Window", bogus):
            frappe.delete_doc("Department Reporting Window", bogus,
                ignore_permissions=True, force=True)
        frappe.db.set_value("Employee", self.emp, "department", bogus)
        with self.assertRaises(week_calendar.MissingReportingWindowError):
            service.ensure_weekly_obligation(self.emp, self.week)

    # ---- 8. DRW disabled ------------------------------------------------
    def test_drw_disabled_raises(self):
        _ensure_drw(TEST_DEPT_A, enabled=0)
        try:
            with self.assertRaises(week_calendar.MissingReportingWindowError):
                service.ensure_weekly_obligation(self.emp, self.week)
        finally:
            _ensure_drw(TEST_DEPT_A, enabled=1)

    # ---- 9. employee changes department uses new deadline next week -----
    def test_department_change_uses_new_dept_next_week(self):
        # Configure DEPT_B with Monday 09:00 deadline -- distinct from DEPT_A.
        _ensure_drw(TEST_DEPT_B, enabled=1, deadline_day="Monday",
            deadline_time="09:00:00", deadline_in_next_week=0)
        frappe.db.set_value("Employee", self.emp, "department", TEST_DEPT_B)
        out = service.ensure_weekly_obligation(self.emp, self.week)
        self.assertEqual(out, "created")
        wtu = frappe.get_all("Weekly Team Update",
            filters={"submitter": self.user, "week_label": self.week["week_label"]},
            fields=["name", "department", "due_at"], limit_page_length=1)
        self.assertEqual(wtu[0].department, TEST_DEPT_B)
        # week_start = 2026-06-15 (Mon); DEPT_B deadline = Mon 09:00 same week.
        self.assertEqual(str(wtu[0].due_at)[:16], "2026-06-15 09:00")

    # ---- 10. terminal-state never recreates ToDo ------------------------
    def test_terminal_submitted_no_todo_recreation(self):
        service.ensure_weekly_obligation(self.emp, self.week)
        wtu = frappe.db.get_value("Weekly Team Update",
            {"submitter": self.user, "week_label": self.week["week_label"]}, "name")
        frappe.db.set_value("Weekly Team Update", wtu, "status", "Submitted")
        for t in frappe.get_all("ToDo",
                filters={"reference_type": "Weekly Team Update",
                         "reference_name": wtu, "status": "Open"},
                pluck="name"):
            frappe.db.set_value("ToDo", t, "status", "Closed")
        out = service.ensure_weekly_obligation(self.emp, self.week)
        self.assertEqual(out, "skipped")
        open_todos = frappe.get_all("ToDo",
            filters={"reference_type": "Weekly Team Update",
                     "reference_name": wtu, "status": "Open"})
        self.assertEqual(len(open_todos), 0)

    def test_terminal_reviewed_no_todo_recreation(self):
        service.ensure_weekly_obligation(self.emp, self.week)
        wtu = frappe.db.get_value("Weekly Team Update",
            {"submitter": self.user, "week_label": self.week["week_label"]}, "name")
        frappe.db.set_value("Weekly Team Update", wtu, "status", "Reviewed")
        for t in frappe.get_all("ToDo",
                filters={"reference_type": "Weekly Team Update",
                         "reference_name": wtu, "status": "Open"},
                pluck="name"):
            frappe.db.set_value("ToDo", t, "status", "Closed")
        out = service.ensure_weekly_obligation(self.emp, self.week)
        self.assertEqual(out, "skipped")
