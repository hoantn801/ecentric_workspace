# Copyright (c) 2026, eCentric and contributors
"""week_start_from_label() must be the exact inverse of compute_week_for().

If these two ever disagree, every deadline derived from a week_label is wrong
by up to seven days -- silently, because a wrong-but-valid deadline looks just
like a right one. The parity test below is the whole point of this file: it
walks real dates through compute_week_for() and back.

Pure calendar arithmetic, no DB.
"""

import unittest
from datetime import date, datetime, timedelta

from ecentric_workspace.weekly_report import week_calendar


class TestWeekStartFromLabel(unittest.TestCase):
    def test_round_trip_matches_compute_week_for(self):
        """Every day across a 3-year span, including both year boundaries."""
        cur = datetime(2025, 1, 1, 9, 0, 0)
        end = datetime(2027, 12, 31, 9, 0, 0)
        checked = 0
        while cur <= end:
            week = week_calendar.compute_week_for(cur)
            back = week_calendar.week_start_from_label(week["week_label"])
            self.assertEqual(
                back, week["week_start_date"],
                "label {0} from {1} mapped back to {2}, expected {3}".format(
                    week["week_label"], cur.date(), back, week["week_start_date"],
                ),
            )
            checked += 1
            cur += timedelta(days=1)
        self.assertGreater(checked, 1000)

    def test_known_labels(self):
        self.assertEqual(week_calendar.week_start_from_label("2026-W38"), date(2026, 9, 14))
        self.assertEqual(week_calendar.week_start_from_label("2026-W01"), date(2025, 12, 29))
        self.assertEqual(week_calendar.week_start_from_label(" 2026-W38 "), date(2026, 9, 14))

    def test_iso_week_53(self):
        """2026 has 53 ISO weeks; 2025 does not. The valid one must work."""
        self.assertEqual(week_calendar.week_start_from_label("2026-W53"), date(2026, 12, 28))
        with self.assertRaises(ValueError):
            week_calendar.week_start_from_label("2025-W53")

    def test_malformed_labels_raise(self):
        for bad in ("", None, "2026-38", "2026W38", "26-W38", "2026-W00",
                    "2026-W54", "2026-Wxx", "yyyy-W38", "2026-W385"):
            with self.assertRaises(ValueError, msg="should reject " + repr(bad)):
                week_calendar.week_start_from_label(bad)
