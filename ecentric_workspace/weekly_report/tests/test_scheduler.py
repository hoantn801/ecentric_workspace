# Copyright (c) 2026, eCentric and contributors
"""Hotfix scheduler tests (Employee-driven)."""

from datetime import datetime

import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.weekly_report import scheduler
from ecentric_workspace.weekly_report import week_calendar

TEST_DEPT = "All Departments"


def _make_user(email):
    if frappe.db.exists("User", email):
        frappe.db.set_value("User", email, "enabled", 1)
        return email
    frappe.get_doc({
        "doctype": "User", "email": email,
        "first_name": "Sched Test", "send_welcome_email": 0, "enabled": 1,
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
        "first_name": "Sched", "last_name": emp_id,
        "gender": "Male", "date_of_birth": "1990-01-01",
        "date_of_joining": "2026-01-01", "status": "Active",
        "user_id": user_email, "department": TEST_DEPT,
    })
    e.insert(ignore_permissions=True)
    return e.name


def _ensure_drw(dept, enabled=1):
    if frappe.db.exists("Department Reporting Window", dept):
        frappe.db.set_value("Department Reporting Window", dept, "enabled", enabled)
        return
    frappe.get_doc({
        "doctype": "Department Reporting Window",
        "department": dept,
        "week_start_day": "Monday", "week_end_day": "Friday",
        "deadline_day": "Friday", "deadline_time": "18:00:00",
        "deadline_in_next_week": 0, "enabled": enabled,
    }).insert(ignore_permissions=True)


class TestScheduler(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _ensure_drw(TEST_DEPT)
        cls.run_dt = datetime(2026, 6, 15, 10, 0, 0)
        cls.week = week_calendar.compute_week_for(cls.run_dt)
        cls.users = []
        cls.emps = []
        for i in (1, 2, 3):
            u = _make_user("wr_hotfix_sched_u%d@example.test" % i)
            e = _make_employee("WR-HOTFIX-SCHED-%03d" % i, u)
            cls.users.append(u)
            cls.emps.append(e)

    def _cleanup(self):
        for u in self.users:
            for n in frappe.get_all("Weekly Team Update",
                    filters={"submitter": u, "week_label": self.week["week_label"]},
                    pluck="name"):
                for t in frappe.get_all("ToDo",
                        filters={"reference_type": "Weekly Team Update",
                                 "reference_name": n}, pluck="name"):
                    frappe.delete_doc("ToDo", t, ignore_permissions=True, force=True)
                frappe.delete_doc("Weekly Team Update", n,
                    ignore_permissions=True, force=True)

    def setUp(self):
        for e, u in zip(self.emps, self.users):
            frappe.db.set_value("Employee", e, {
                "status": "Active", "user_id": u, "department": TEST_DEPT,
            })
            frappe.db.set_value("User", u, "enabled", 1)
        _ensure_drw(TEST_DEPT, enabled=1)
        self._cleanup()

    def tearDown(self):
        self._cleanup()

    def test_first_run_creates_then_second_reuses(self):
        s1 = scheduler.generate_weekly_obligations(
            run_date=self.run_dt, employee_names=self.emps)
        self.assertEqual(s1["processed"], 3)
        self.assertEqual(s1["created"], 3)
        self.assertEqual(s1["errored"], 0)
        s2 = scheduler.generate_weekly_obligations(
            run_date=self.run_dt, employee_names=self.emps)
        self.assertEqual(s2["created"], 0)
        self.assertEqual(s2["reused"], 3)
        for u in self.users:
            wtus = frappe.get_all("Weekly Team Update",
                filters={"submitter": u, "week_label": self.week["week_label"]})
            self.assertEqual(len(wtus), 1)

    def test_inactive_employee_filtered_out(self):
        # Inactive Employees are filtered by get_all(status="Active"),
        # so processed never sees them.
        frappe.db.set_value("Employee", self.emps[0], "status", "Inactive")
        stats = scheduler.generate_weekly_obligations(
            run_date=self.run_dt, employee_names=self.emps)
        self.assertEqual(stats["processed"], 2)
        self.assertEqual(stats["created"], 2)

    def test_employee_names_filter(self):
        stats = scheduler.generate_weekly_obligations(
            run_date=self.run_dt, employee_names=[self.emps[0]])
        self.assertEqual(stats["processed"], 1)

    def test_drw_disabled_marks_skipped(self):
        """Disabled DRW = controlled skipped, NOT errored.

        errored is reserved for unexpected failures (DB, assignment, rollback).
        """
        _ensure_drw(TEST_DEPT, enabled=0)
        try:
            stats = scheduler.generate_weekly_obligations(
                run_date=self.run_dt, employee_names=[self.emps[0]])
            self.assertEqual(stats["drw_missing"], 1)
            self.assertEqual(stats["skipped"], 1)
            self.assertEqual(stats["errored"], 0)
        finally:
            _ensure_drw(TEST_DEPT, enabled=1)

    def test_rollback_failure_aborts_batch(self):
        """If savepoint rollback raises, the scheduler batch aborts."""
        _ensure_drw(TEST_DEPT, enabled=0)  # forces MissingReportingWindowError
        orig_rollback = frappe.db.rollback
        def _bad_rollback(*a, **kw):
            if kw.get("save_point") or (a and isinstance(a[0], str)):
                raise RuntimeError("simulated rollback failure")
            return orig_rollback(*a, **kw)
        frappe.db.rollback = _bad_rollback
        try:
            with self.assertRaises(RuntimeError):
                scheduler.generate_weekly_obligations(
                    run_date=self.run_dt, employee_names=self.emps)
        finally:
            frappe.db.rollback = orig_rollback
            _ensure_drw(TEST_DEPT, enabled=1)

    # ===== Rollout kill-switch tests ======================================

    def _set_auto_flag(self, value):
        """Set frappe.conf in-process for the duration of one test."""
        # frappe.conf is a dict-like object; mutate then restore.
        self._orig_flag = frappe.conf.get("enable_weekly_report_auto_generation")
        frappe.conf["enable_weekly_report_auto_generation"] = value

    def _restore_auto_flag(self):
        if getattr(self, "_orig_flag", None) is None:
            try:
                del frappe.conf["enable_weekly_report_auto_generation"]
            except KeyError:
                pass
        else:
            frappe.conf["enable_weekly_report_auto_generation"] = self._orig_flag

    def test_kill_switch_off_auto_run_returns_disabled(self):
        """No employee_names + auto flag OFF -> no Employees processed."""
        # Ensure flag is absent/0
        if "enable_weekly_report_auto_generation" in frappe.conf:
            self._set_auto_flag(0)
        try:
            stats = scheduler.generate_weekly_obligations(run_date=self.run_dt)
            self.assertTrue(stats.get("disabled"))
            self.assertEqual(stats["processed"], 0)
            self.assertEqual(stats["created"], 0)
        finally:
            self._restore_auto_flag()
        # And: no WTUs created.
        for u in self.users:
            wtus = frappe.get_all("Weekly Team Update",
                filters={"submitter": u, "week_label": self.week["week_label"]})
            self.assertEqual(len(wtus), 0)

    def test_kill_switch_off_pilot_with_employee_names_still_runs(self):
        """employee_names ALWAYS bypasses the kill-switch (pilot path)."""
        self._set_auto_flag(0)
        try:
            stats = scheduler.generate_weekly_obligations(
                run_date=self.run_dt,
                employee_names=[self.emps[0]])
            self.assertFalse(stats.get("disabled", False))
            self.assertEqual(stats["processed"], 1)
            self.assertEqual(stats["created"], 1)
        finally:
            self._restore_auto_flag()

    def test_kill_switch_on_auto_run_processes_active_employees(self):
        """Flag = 1 + no employee_names -> full batch over Active Employees."""
        self._set_auto_flag(1)
        try:
            stats = scheduler.generate_weekly_obligations(run_date=self.run_dt)
            self.assertFalse(stats.get("disabled", False))
            self.assertGreaterEqual(stats["processed"], 3)
            self.assertGreaterEqual(stats["created"], 3)
        finally:
            self._restore_auto_flag()

    def test_kill_switch_null_or_invalid_treated_as_off(self):
        """cint('') / cint(None) / cint('abc') -> 0 -> auto path disabled."""
        for bad_value in (None, "", "abc", "0", 0, False):
            self._set_auto_flag(bad_value)
            try:
                stats = scheduler.generate_weekly_obligations(run_date=self.run_dt)
                self.assertTrue(stats.get("disabled"),
                    "Flag value %r should be treated as OFF" % (bad_value,))
            finally:
                self._restore_auto_flag()


# ===== Regression test: production Management - EC case =====================
# Bug: compute_due_at did not fetch DRW.enabled, so w.get("enabled") was always
# None, raising MissingReportingWindowError even for valid enabled DRWs.
# Production data that triggered: Employee HR-EMP-00002 (Active), department
# Management - EC, User hoan.tran@ecentric.vn enabled=1, DRW Management - EC
# enabled=1, deadline_day=Monday, deadline_time=11:00:00, deadline_in_next_week=1.

REGRESSION_DEPT = "Management - EC"
REGRESSION_USER = "wr_reg_mgmt_user@example.test"
REGRESSION_EMP_ID = "WR-REG-MGMT-001"


def _ensure_dept(dept):
    if frappe.db.exists("Department", dept):
        return
    frappe.get_doc({
        "doctype": "Department", "department_name": dept,
    }).insert(ignore_permissions=True)


def _ensure_drw_exact(dept, deadline_day, deadline_time,
                     deadline_in_next_week, enabled=1):
    """Match production DRW config exactly."""
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
        "deadline_in_next_week": deadline_in_next_week,
        "enabled": enabled,
    }).insert(ignore_permissions=True)


class TestRegressionDrwEnabledFieldFetch(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _ensure_dept(REGRESSION_DEPT)
        cls.user = _make_user(REGRESSION_USER)
        existing_emp = frappe.db.get_value("Employee",
            {"employee_number": REGRESSION_EMP_ID}, "name")
        if existing_emp:
            frappe.db.set_value("Employee", existing_emp, {
                "status": "Active", "user_id": cls.user,
                "department": REGRESSION_DEPT,
            })
            cls.emp = existing_emp
        else:
            e = frappe.get_doc({
                "doctype": "Employee",
                "employee_number": REGRESSION_EMP_ID,
                "first_name": "Reg", "last_name": "Mgmt",
                "gender": "Male", "date_of_birth": "1990-01-01",
                "date_of_joining": "2026-01-01", "status": "Active",
                "user_id": cls.user, "department": REGRESSION_DEPT,
            })
            e.insert(ignore_permissions=True)
            cls.emp = e.name
        _ensure_drw_exact(REGRESSION_DEPT,
            deadline_day="Monday", deadline_time="11:00:00",
            deadline_in_next_week=1, enabled=1)
        cls.run_dt = datetime(2026, 6, 15, 10, 0, 0)
        cls.week = week_calendar.compute_week_for(cls.run_dt)

    def _cleanup(self):
        for n in frappe.get_all("Weekly Team Update",
                filters={"submitter": self.user,
                         "week_label": self.week["week_label"]},
                pluck="name"):
            for t in frappe.get_all("ToDo",
                    filters={"reference_type": "Weekly Team Update",
                             "reference_name": n}, pluck="name"):
                frappe.delete_doc("ToDo", t, ignore_permissions=True, force=True)
            frappe.delete_doc("Weekly Team Update", n,
                ignore_permissions=True, force=True)

    def setUp(self):
        frappe.db.set_value("Employee", self.emp, {
            "status": "Active", "user_id": self.user,
            "department": REGRESSION_DEPT,
        })
        frappe.db.set_value("User", self.user, "enabled", 1)
        _ensure_drw_exact(REGRESSION_DEPT,
            deadline_day="Monday", deadline_time="11:00:00",
            deadline_in_next_week=1, enabled=1)
        self._cleanup()

    def tearDown(self):
        self._cleanup()

    def test_production_management_dept_monday_next_week(self):
        """Exact production case: enabled=1 DRW must NOT raise drw_missing.

        Pre-fix: w.get('enabled') returned None (field not fetched), so the
        check `if not w.get('enabled')` raised MissingReportingWindowError
        for every DRW, including enabled=1 ones.
        Post-fix: 'enabled' is in the get_value field list, so the check
        sees the real value (1) and passes.
        """
        stats = scheduler.generate_weekly_obligations(
            run_date=self.run_dt, employee_names=[self.emp])
        self.assertEqual(stats["processed"], 1,
            "Employee must be processed (was eligible).")
        self.assertEqual(stats["created"], 1,
            "WTU Draft must be created (DRW is valid).")
        self.assertEqual(stats["skipped"], 0,
            "Must NOT be skipped (DRW is enabled).")
        self.assertEqual(stats["errored"], 0,
            "No unexpected error.")
        self.assertEqual(stats["drw_missing"], 0,
            "DRW exists and is enabled -- must NOT mark drw_missing.")

        # Verify the WTU was actually created with the right due_at:
        # week_start = 2026-06-15 (Mon) ; deadline_day=Monday + next_week=1
        # -> deadline_date = 2026-06-22 (Mon of W26) at 11:00.
        wtu = frappe.get_all("Weekly Team Update",
            filters={"submitter": self.user,
                     "week_label": self.week["week_label"]},
            fields=["name", "due_at", "department"], limit_page_length=1)
        self.assertEqual(len(wtu), 1)
        self.assertEqual(wtu[0].department, REGRESSION_DEPT)
        self.assertEqual(str(wtu[0].due_at)[:16], "2026-06-22 11:00")

    def test_drw_disabled_still_skipped_post_fix(self):
        """After the fix, enabled=0 DRW must STILL skip + mark drw_missing.

        This is the inverse check: the fix should not break the legitimate
        disabled-DRW path.
        """
        _ensure_drw_exact(REGRESSION_DEPT,
            deadline_day="Monday", deadline_time="11:00:00",
            deadline_in_next_week=1, enabled=0)
        try:
            stats = scheduler.generate_weekly_obligations(
                run_date=self.run_dt, employee_names=[self.emp])
            self.assertEqual(stats["processed"], 1)
            self.assertEqual(stats["created"], 0)
            self.assertEqual(stats["skipped"], 1)
            self.assertEqual(stats["drw_missing"], 1)
            self.assertEqual(stats["errored"], 0)
        finally:
            _ensure_drw_exact(REGRESSION_DEPT,
                deadline_day="Monday", deadline_time="11:00:00",
                deadline_in_next_week=1, enabled=1)
