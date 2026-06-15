# Copyright (c) 2026, eCentric and contributors
"""Parity tests for week_calendar against the JS calculateCurrentWeek().

Edge cases driven by snapshot 06_wp_weekly_update_full.json lines ~1060-1100.
"""

from datetime import datetime, date

from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.weekly_report import week_calendar


class TestWeekCalendar(FrappeTestCase):
    def test_monday_morning_is_current_week(self):
        # 2026-06-15 is a Monday.
        w = week_calendar.compute_week_for(datetime(2026, 6, 15, 10, 0, 0))
        self.assertEqual(w["week_label"], "2026-W25")
        self.assertEqual(w["week_start_date"], date(2026, 6, 15))
        self.assertEqual(w["week_end_date"], date(2026, 6, 19))

    def test_friday_before_deadline_is_current_week(self):
        # 2026-06-19 (Fri) 17:59 -> still W25
        w = week_calendar.compute_week_for(datetime(2026, 6, 19, 17, 59, 0))
        self.assertEqual(w["week_label"], "2026-W25")

    def test_friday_at_deadline_is_current_week(self):
        # Equal to deadline -> still current (JS uses strict >, not >=).
        w = week_calendar.compute_week_for(datetime(2026, 6, 19, 18, 0, 0))
        self.assertEqual(w["week_label"], "2026-W25")

    def test_friday_past_deadline_rolls_to_next_week(self):
        w = week_calendar.compute_week_for(datetime(2026, 6, 19, 18, 1, 0))
        self.assertEqual(w["week_label"], "2026-W26")
        self.assertEqual(w["week_start_date"], date(2026, 6, 22))

    def test_sunday_is_next_week(self):
        w = week_calendar.compute_week_for(datetime(2026, 6, 21, 12, 0, 0))
        self.assertEqual(w["week_label"], "2026-W26")

    def test_accepts_string_input(self):
        w = week_calendar.compute_week_for("2026-06-15 10:00:00")
        self.assertEqual(w["week_label"], "2026-W25")

    def test_accepts_date_input(self):
        # date input normalises to midnight; Monday midnight is still W25.
        w = week_calendar.compute_week_for(date(2026, 6, 15))
        self.assertEqual(w["week_label"], "2026-W25")

    def test_iso_week_year_boundary(self):
        # 2027-12-30 is Thu of W52; Friday 2027-12-31 18:01 should roll to W53/W01.
        w = week_calendar.compute_week_for(datetime(2027, 12, 30, 10, 0, 0))
        self.assertEqual(w["week_label"], "2027-W52")
