# Copyright (c) 2026, eCentric and contributors
"""due_backfill: the on-time / late / no-window decision, and dry-run safety.

Two properties are worth a test here and they are both about not doing harm:

  * dry_run must write NOTHING. It is the default, and the whole point of it is
    that somebody can look at `would_be_late` before deciding.
  * a row whose author comes out late must be counted as such, and must be
    skippable. The missing deadline was our bug; silently costing someone their
    SLA number while fixing it would be the worse outcome.

No bench, no DB: frappe's three entry points are stubbed, same spirit as
test_submit_service.py.
"""

import unittest
from datetime import datetime

from ecentric_workspace.weekly_report import due_backfill, week_calendar

DUE = datetime(2026, 9, 18, 18, 0, 0)   # Friday 18:00 of 2026-W38
DEPT_OK = "Dept-With-DRW"


def _row(name, submitted_at, employee="E1", key=""):
    return {
        "name": name, "employee": employee, "week_label": "2026-W38",
        "department": "display string", "status": "Submitted",
        "submitted_at": submitted_at, "obligation_key": key,
    }


class _Saved(object):
    """Records every save() so a dry run can be proven to write nothing."""

    def __init__(self):
        self.rows = []


class _FakeDoc(object):
    def __init__(self, name, key, sink):
        self.name = name
        self.obligation_key = key
        self.due_at = None
        self._sink = sink

    def save(self, ignore_permissions=False):
        self._sink.rows.append((self.name, self.due_at, self.obligation_key))


class DueBackfillTestCase(unittest.TestCase):
    def setUp(self):
        self.saved = _Saved()
        self.rows = []
        self.emp_dept = {"E1": DEPT_OK, "E2": None}

        self._orig = {
            "frappe": due_backfill.frappe,
            "due_at_for_label": week_calendar.due_at_for_label,
        }

        test = self

        class _DB(object):
            def get_value(self, doctype, name, field=None, as_dict=False):
                if doctype == "Employee":
                    return test.emp_dept.get(name)
                return None

        class _Utils(object):
            def get_datetime(self, value):
                if isinstance(value, datetime):
                    return value
                return datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S")

        class _Frappe(object):
            db = _DB()
            utils = _Utils()

            def get_all(self, doctype, **kwargs):
                return list(test.rows)

            def get_doc(self, doctype, name):
                key = next(
                    (r["obligation_key"] for r in test.rows if r["name"] == name), ""
                )
                return _FakeDoc(name, key, test.saved)

            def log_error(self, *args, **kwargs):
                return None

        due_backfill.frappe = _Frappe()

        def _due(week_label, department):
            if department != DEPT_OK:
                raise week_calendar.MissingReportingWindowError(
                    "DRW missing for " + str(department)
                )
            return DUE

        week_calendar.due_at_for_label = _due

    def tearDown(self):
        due_backfill.frappe = self._orig["frappe"]
        week_calendar.due_at_for_label = self._orig["due_at_for_label"]

    # ---------------------------------------------------------------- tests --
    def test_dry_run_writes_nothing(self):
        self.rows = [_row("on-time", "2026-09-18 09:00:00"),
                     _row("late", "2026-09-19 23:00:00")]
        report = due_backfill.preview(weeks=["2026-W38"])
        self.assertEqual(report["scanned"], 2)
        self.assertEqual(report["would_fill"], 2)
        self.assertEqual(report["would_be_late"], 1)
        self.assertEqual(report["written"], 0)
        self.assertEqual(self.saved.rows, [], "dry run must not touch the DB")

    def test_late_is_detected_on_the_right_side_of_the_boundary(self):
        # One second either side of the deadline decides someone's SLA number.
        self.rows = [_row("just-in", "2026-09-18 17:59:59"),
                     _row("exactly", "2026-09-18 18:00:00"),
                     _row("just-out", "2026-09-18 18:00:01")]
        report = due_backfill.preview(weeks=["2026-W38"])
        self.assertEqual(report["would_be_late"], 1)
        self.assertEqual([r["name"] for r in report["late_rows"]], ["just-out"])

    def test_skip_if_late_leaves_late_rows_alone(self):
        self.rows = [_row("on-time", "2026-09-18 09:00:00"),
                     _row("late", "2026-09-19 23:00:00")]
        report = due_backfill.backfill(
            weeks=["2026-W38"], dry_run=False, skip_if_late=True
        )
        self.assertEqual(report["written"], 1)
        self.assertEqual(report["skipped_late"], 1)
        self.assertEqual([r[0] for r in self.saved.rows], ["on-time"])

    def test_write_fills_due_at_and_missing_obligation_key(self):
        self.rows = [_row("no-key", "2026-09-18 09:00:00", key="")]
        due_backfill.backfill(weeks=["2026-W38"], dry_run=False)
        self.assertEqual(self.saved.rows[0][1], DUE)
        self.assertEqual(self.saved.rows[0][2], "E1::2026-W38")

    def test_existing_obligation_key_is_not_overwritten(self):
        self.rows = [_row("has-key", "2026-09-18 09:00:00", key="LEGACY::KEY")]
        due_backfill.backfill(weeks=["2026-W38"], dry_run=False)
        self.assertEqual(self.saved.rows[0][2], "LEGACY::KEY")

    def test_missing_window_is_reported_never_guessed(self):
        """No DRW -> no deadline. Inventing one to score somebody is worse."""
        self.rows = [_row("no-drw", "2026-09-18 09:00:00", employee="E2")]
        report = due_backfill.backfill(weeks=["2026-W38"], dry_run=False)
        self.assertEqual(report["no_window"], 1)
        self.assertEqual(report["would_fill"], 0)
        self.assertEqual(report["written"], 0)
        self.assertEqual(self.saved.rows, [])
        self.assertIn("DRW missing", report["no_window_rows"][0]["reason"])

    def test_row_never_submitted_is_not_late(self):
        self.rows = [_row("draft", None)]
        report = due_backfill.preview(weeks=["2026-W38"])
        self.assertEqual(report["would_fill"], 1)
        self.assertEqual(report["would_be_late"], 0)
