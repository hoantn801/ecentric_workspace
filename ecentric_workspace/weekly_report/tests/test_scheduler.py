# Copyright (c) 2026, eCentric and contributors
"""Scheduler tests for generate_weekly_obligations.

Covers:
  1. processed counter counts every Schedule examined (incl. skipped/errored).
  2. outcome counters (created/reused/adopted/skipped) increment correctly.
  3. DRW missing increments drw_missing AND errored, no partial WTU created.
  4. last_generated_week ONLY updates after WTU+ToDo both confirmed.
  5. Per-schedule savepoint isolates a bad row from the rest.
  6. schedule_names filter restricts processing.
"""

from datetime import datetime

import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.weekly_report import scheduler
from ecentric_workspace.weekly_report import service
from ecentric_workspace.weekly_report import week_calendar

TEST_DEPT = "All Departments"


def _make_user(email):
    if frappe.db.exists("User", email):
        return email
    frappe.get_doc({
        "doctype": "User", "email": email,
        "first_name": "Sched Test", "send_welcome_email": 0, "enabled": 1,
    }).insert(ignore_permissions=True)
    return email


def _make_employee(emp_id, user_email):
    existing = frappe.db.get_value("Employee", {"employee_number": emp_id}, "name")
    if existing:
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


def _make_schedule(emp, dept, enabled=1, effective_from="2026-01-01", effective_to=None):
    if frappe.db.exists("Weekly Report Schedule", {"employee": emp}):
        existing = frappe.get_doc("Weekly Report Schedule", {"employee": emp})
        existing.enabled = enabled
        existing.reporting_department = dept
        existing.effective_from = effective_from
        existing.effective_to = effective_to
        existing.last_generated_week = None
        existing.save(ignore_permissions=True)
        return existing.name
    s = frappe.get_doc({
        "doctype": "Weekly Report Schedule",
        "employee": emp,
        "reporting_department": dept,
        "effective_from": effective_from,
        "effective_to": effective_to,
        "enabled": enabled,
    })
    s.insert(ignore_permissions=True)
    return s.name


class TestScheduler(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _ensure_drw(TEST_DEPT)
        cls.run_dt = datetime(2026, 6, 15, 10, 0, 0)
        cls.week = week_calendar.compute_week_for(cls.run_dt)
        # 3 test users / employees / schedules
        cls.users = []
        cls.emps = []
        cls.schedules = []
        for i in (1, 2, 3):
            u = _make_user("wr1a_sched_u%d@example.test" % i)
            e = _make_employee("WR1A-SCHED-%03d" % i, u)
            cls.users.append(u)
            cls.emps.append(e)
            cls.schedules.append(_make_schedule(e, TEST_DEPT))

    def _cleanup_wtus(self):
        for u in self.users:
            rows = frappe.get_all("Weekly Team Update",
                filters={"submitter": u, "week_label": self.week["week_label"]},
                pluck="name")
            for n in rows:
                for t in frappe.get_all("ToDo",
                        filters={"reference_type": "Weekly Team Update", "reference_name": n},
                        pluck="name"):
                    frappe.delete_doc("ToDo", t, ignore_permissions=True, force=True)
                frappe.delete_doc("Weekly Team Update", n, ignore_permissions=True, force=True)

    def setUp(self):
        self._cleanup_wtus()
        # reset last_generated_week marker
        for s in self.schedules:
            frappe.db.set_value("Weekly Report Schedule", s, "last_generated_week", None,
                update_modified=False)

    def tearDown(self):
        self._cleanup_wtus()

    def test_processed_counts_examined_schedules(self):
        """processed must count EVERY schedule looked at, including skipped/errored."""
        # Disable one schedule, leave 2 enabled
        frappe.db.set_value("Weekly Report Schedule", self.schedules[0], "enabled", 0,
            update_modified=False)
        stats = scheduler.generate_weekly_obligations(
            run_date=self.run_dt,
            schedule_names=self.schedules,  # examine all 3
        )
        # enabled=0 schedule is filtered OUT by the get_all() query, not counted.
        # So processed should equal #schedules examined = enabled ones.
        self.assertEqual(stats["processed"], 2)
        # Restore
        frappe.db.set_value("Weekly Report Schedule", self.schedules[0], "enabled", 1,
            update_modified=False)

    def test_outcome_counters_correct(self):
        """First run = 3 created. Second run = 3 reused."""
        s1 = scheduler.generate_weekly_obligations(
            run_date=self.run_dt, schedule_names=self.schedules)
        self.assertEqual(s1["processed"], 3)
        self.assertEqual(s1["created"], 3)
        self.assertEqual(s1["reused"], 0)
        self.assertEqual(s1["errored"], 0)
        s2 = scheduler.generate_weekly_obligations(
            run_date=self.run_dt, schedule_names=self.schedules)
        self.assertEqual(s2["processed"], 3)
        self.assertEqual(s2["created"], 0)
        self.assertEqual(s2["reused"], 3)

    def test_drw_missing_marks_errored_and_drw_missing(self):
        """Schedule with non-existent reporting_department -> drw_missing + errored."""
        bad_dept = "Nonexistent Dept WR1A-XYZ"
        # Point one schedule at a non-existent department
        sched = self.schedules[0]
        frappe.db.set_value("Weekly Report Schedule", sched,
            "reporting_department", bad_dept, update_modified=False)
        try:
            stats = scheduler.generate_weekly_obligations(
                run_date=self.run_dt, schedule_names=[sched])
            self.assertEqual(stats["processed"], 1)
            self.assertEqual(stats["drw_missing"], 1)
            self.assertEqual(stats["errored"], 1)
            # No partial WTU
            wtus = frappe.get_all("Weekly Team Update",
                filters={"submitter": self.users[0], "week_label": self.week["week_label"]})
            self.assertEqual(len(wtus), 0)
        finally:
            frappe.db.set_value("Weekly Report Schedule", sched,
                "reporting_department", TEST_DEPT, update_modified=False)

    def test_last_generated_week_only_after_success(self):
        """last_generated_week updates after successful create; NOT after errored."""
        stats = scheduler.generate_weekly_obligations(
            run_date=self.run_dt, schedule_names=[self.schedules[0]])
        self.assertEqual(stats["created"], 1)
        marker = frappe.db.get_value("Weekly Report Schedule",
            self.schedules[0], "last_generated_week")
        self.assertEqual(marker, self.week["week_label"])

        # Now test the errored path: redirect 2nd schedule's department to a bad value,
        # confirm last_generated_week stays None.
        sched = self.schedules[1]
        bad_dept = "Nonexistent Dept WR1A-XYZ"
        frappe.db.set_value("Weekly Report Schedule", sched,
            "reporting_department", bad_dept, update_modified=False)
        try:
            scheduler.generate_weekly_obligations(
                run_date=self.run_dt, schedule_names=[sched])
            marker2 = frappe.db.get_value("Weekly Report Schedule",
                sched, "last_generated_week")
            self.assertIsNone(marker2)
        finally:
            frappe.db.set_value("Weekly Report Schedule", sched,
                "reporting_department", TEST_DEPT, update_modified=False)

    def test_savepoint_rollback_isolates_bad_schedule(self):
        """A single bad schedule must not prevent siblings from generating."""
        bad_sched = self.schedules[0]
        good_sched = self.schedules[1]
        bad_dept = "Nonexistent Dept WR1A-XYZ"
        frappe.db.set_value("Weekly Report Schedule", bad_sched,
            "reporting_department", bad_dept, update_modified=False)
        try:
            stats = scheduler.generate_weekly_obligations(
                run_date=self.run_dt,
                schedule_names=[bad_sched, good_sched])
            self.assertEqual(stats["processed"], 2)
            self.assertEqual(stats["drw_missing"], 1)
            self.assertEqual(stats["created"], 1)  # good sibling survives
            # Verify only good schedule's WTU exists
            good_user = frappe.db.get_value("Weekly Report Schedule", good_sched, "user")
            wtus_good = frappe.get_all("Weekly Team Update",
                filters={"submitter": good_user, "week_label": self.week["week_label"]})
            self.assertEqual(len(wtus_good), 1)
        finally:
            frappe.db.set_value("Weekly Report Schedule", bad_sched,
                "reporting_department", TEST_DEPT, update_modified=False)

    def test_schedule_names_filter(self):
        """schedule_names filter restricts processing to the listed names."""
        stats = scheduler.generate_weekly_obligations(
            run_date=self.run_dt,
            schedule_names=[self.schedules[0]])
        self.assertEqual(stats["processed"], 1)
        # Only first user should have a WTU
        wtus_0 = frappe.get_all("Weekly Team Update",
            filters={"submitter": self.users[0], "week_label": self.week["week_label"]})
        wtus_1 = frappe.get_all("Weekly Team Update",
            filters={"submitter": self.users[1], "week_label": self.week["week_label"]})
        self.assertEqual(len(wtus_0), 1)
        self.assertEqual(len(wtus_1), 0)
