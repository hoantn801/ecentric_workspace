# Copyright (c) 2026, eCentric and contributors
"""Test tang domain - chay duoc BANG python3 TRAN, khong can bench.

    python3 -m unittest ecentric_workspace.sla.tests.test_domain -v

Do la yeu cau thiet ke, khong phai tien nghi: cong thuc %SLA la thu se bi chat
van boi nguoi bi tru diem, va mot cong thuc chi kiem chung duoc bang cach dung
bench len thi trong thuc te se khong ai kiem chung ca.
"""
import unittest
from datetime import datetime

from ecentric_workspace.sla.constants import (
    DUE_BUSINESS_HOURS, DUE_CALENDAR_HOURS, DUE_EXPLICIT, DUE_FIXED_TIME,
    GROUP_APPROVAL, GROUP_ATTENDANCE, GROUP_TASK, STATUS_EXCLUDED, STATUS_LATE,
    STATUS_MET, STATUS_MISSED, STATUS_OPEN,
)
from ecentric_workspace.sla.domain import due_rules, scoring

D = datetime


class TestDueRules(unittest.TestCase):
    def test_calendar_hours(self):
        due = due_rules.resolve_due(DUE_CALENDAR_HOURS, D(2026, 9, 16, 10, 0),
                                    duration_hours=4)
        self.assertEqual(due, D(2026, 9, 16, 14, 0))

    def test_calendar_hours_with_grace(self):
        due = due_rules.resolve_due(DUE_CALENDAR_HOURS, D(2026, 9, 16, 10, 0),
                                    duration_hours=4, grace_minutes=5)
        self.assertEqual(due, D(2026, 9, 16, 14, 5))

    def test_fixed_time_same_day(self):
        due = due_rules.resolve_due(DUE_FIXED_TIME, D(2026, 9, 16, 8, 3),
                                    fixed_time="23:59:00")
        self.assertEqual(due, D(2026, 9, 16, 23, 59))

    def test_fixed_time_next_day(self):
        due = due_rules.resolve_due(DUE_FIXED_TIME, D(2026, 9, 16, 8, 3),
                                    fixed_time="09:00:00", offset_days=1,
                                    grace_minutes=5)
        self.assertEqual(due, D(2026, 9, 17, 9, 5))

    def test_explicit(self):
        due = due_rules.resolve_due(DUE_EXPLICIT, None,
                                    explicit_due="2026-09-20 17:00:00")
        self.assertEqual(due, D(2026, 9, 20, 17, 0))

    def test_business_hours_delegates(self):
        calls = []

        def fake(start, hours):
            calls.append((start, hours))
            return D(2026, 9, 17, 9, 0)

        due = due_rules.resolve_due(DUE_BUSINESS_HOURS, D(2026, 9, 16, 16, 0),
                                    duration_hours=4, business_due_fn=fake)
        self.assertEqual(due, D(2026, 9, 17, 9, 0))
        self.assertEqual(calls, [(D(2026, 9, 16, 16, 0), 4.0)])

    def test_missing_params_raise(self):
        with self.assertRaises(due_rules.DueRuleError):
            due_rules.resolve_due(DUE_CALENDAR_HOURS, D(2026, 9, 16), duration_hours=0)
        with self.assertRaises(due_rules.DueRuleError):
            due_rules.resolve_due(DUE_FIXED_TIME, D(2026, 9, 16))
        with self.assertRaises(due_rules.DueRuleError):
            due_rules.resolve_due(DUE_BUSINESS_HOURS, D(2026, 9, 16), duration_hours=4)
        with self.assertRaises(due_rules.DueRuleError):
            due_rules.resolve_due("Khong Ton Tai", D(2026, 9, 16), duration_hours=4)

    def test_period_of_uses_open_time(self):
        self.assertEqual(due_rules.period_of(D(2026, 9, 30, 23, 59)), "2026-09")
        self.assertEqual(due_rules.period_of("2026-10-01 00:00:00"), "2026-10")

    def test_period_bounds_wraps_year(self):
        lo, hi = due_rules.period_bounds("2026-12")
        self.assertEqual((lo, hi), (D(2026, 12, 1), D(2027, 1, 1)))


class TestClassify(unittest.TestCase):
    def test_on_time(self):
        st, late = scoring.classify_close(D(2026, 9, 16, 12, 0), D(2026, 9, 16, 11, 0))
        self.assertEqual((st, late), (STATUS_MET, 0))

    def test_exactly_on_deadline_is_met(self):
        st, _ = scoring.classify_close(D(2026, 9, 16, 12, 0), D(2026, 9, 16, 12, 0))
        self.assertEqual(st, STATUS_MET)

    def test_late(self):
        st, late = scoring.classify_close(D(2026, 9, 16, 12, 0), D(2026, 9, 16, 13, 30))
        self.assertEqual(st, STATUS_LATE)
        self.assertEqual(late, 5400)

    def test_pause_pushes_deadline_out(self):
        st, late = scoring.classify_close(D(2026, 9, 16, 12, 0), D(2026, 9, 16, 13, 30),
                                          paused_seconds=7200)
        self.assertEqual((st, late), (STATUS_MET, 0))

    def test_no_deadline_is_excluded_not_met(self):
        """57/60 buoc duyet hien chua cau hinh SLA. Neu 'khong co han' = 'dung
        han' thi ngay hom bat he thong len, nhom Phan hoi phe duyet hien 100%
        cho tat ca - mot con so dep, sai, va khong ai co ly do de nghi ngo."""
        st, late = scoring.classify_close(None, D(2026, 9, 16, 13, 30))
        self.assertEqual((st, late), (STATUS_EXCLUDED, 0))

    def test_no_deadline_never_enters_denominator(self):
        rows = [{"group_key": GROUP_APPROVAL, "status": STATUS_OPEN,
                 "due_at": None, "paused_seconds": 0}] * 20
        agg = scoring.aggregate(rows, now=D(2026, 9, 16))
        g = agg["groups"][GROUP_APPROVAL]
        self.assertEqual(g["scored"], 0)
        self.assertIsNone(g["rate"])
        self.assertEqual(g["no_policy"], 20)

    def test_lateness_can_be_measured_in_business_time(self):
        # Han 17h thu Sau, dong 9h thu Hai. Do bang dong ho = 64 gio; do bang
        # gio lam viec = 30 phut. Hai con so, mot su that.
        st, late = scoring.classify_close(
            D(2026, 9, 18, 17, 0), D(2026, 9, 21, 9, 0),
            elapsed_fn=lambda a, b: 1800)
        self.assertEqual((st, late), (STATUS_LATE, 1800))


class TestBreach(unittest.TestCase):
    """Lo hong nguy hiem nhat cua he: khong dong viec = khong bi tru."""

    def test_open_past_due_is_breached(self):
        self.assertTrue(scoring.is_breached(STATUS_OPEN, D(2026, 9, 16, 12, 0),
                                            D(2026, 9, 16, 12, 1)))

    def test_open_before_due_is_not(self):
        self.assertFalse(scoring.is_breached(STATUS_OPEN, D(2026, 9, 16, 12, 0),
                                             D(2026, 9, 16, 11, 59)))

    def test_closed_row_never_breached(self):
        self.assertFalse(scoring.is_breached(STATUS_MET, D(2026, 9, 16, 12, 0),
                                             D(2026, 9, 30)))

    def test_effective_status_counts_open_overdue_as_missed(self):
        row = {"status": STATUS_OPEN, "due_at": D(2026, 9, 10), "paused_seconds": 0}
        self.assertEqual(scoring.effective_status(row, D(2026, 9, 16)), STATUS_MISSED)

    def test_open_overdue_enters_denominator(self):
        rows = [{"group_key": GROUP_APPROVAL, "status": STATUS_OPEN,
                 "due_at": D(2026, 9, 10), "paused_seconds": 0}] * 3
        rows += [{"group_key": GROUP_APPROVAL, "status": STATUS_MET,
                  "due_at": D(2026, 9, 10), "paused_seconds": 0}] * 7
        agg = scoring.aggregate(rows, now=D(2026, 9, 16))
        g = agg["groups"][GROUP_APPROVAL]
        self.assertEqual(g["scored"], 10)
        self.assertEqual(g["missed"], 3)
        self.assertEqual(g["rate"], 70.0)


def _rows(group, **counts):
    out = []
    for status, n in counts.items():
        st = {"met": STATUS_MET, "late": STATUS_LATE, "missed": STATUS_MISSED,
              "excluded": STATUS_EXCLUDED}[status]
        out += [{"group_key": group, "status": st, "due_at": D(2026, 9, 1),
                 "paused_seconds": 0}] * n
    return out


class TestAggregate(unittest.TestCase):
    def test_rate_and_denominator(self):
        agg = scoring.aggregate(_rows(GROUP_APPROVAL, met=8, late=1, missed=1,
                                      excluded=5), now=D(2026, 9, 16))
        g = agg["groups"][GROUP_APPROVAL]
        self.assertEqual(g["scored"], 10)
        self.assertEqual(g["excluded"], 5)
        self.assertEqual(g["rate"], 80.0)

    def test_below_min_sample_has_no_rate(self):
        agg = scoring.aggregate(_rows(GROUP_APPROVAL, met=1), now=D(2026, 9, 16))
        g = agg["groups"][GROUP_APPROVAL]
        self.assertIsNone(g["rate"])
        self.assertFalse(g["enough_sample"])
        self.assertEqual(g["ontime"], 1)

    def test_task_group_measured_but_excluded_from_overall(self):
        rows = _rows(GROUP_APPROVAL, met=10) + _rows(GROUP_TASK, missed=10)
        agg = scoring.aggregate(rows, now=D(2026, 9, 16))
        self.assertEqual(agg["groups"][GROUP_TASK]["rate"], 0.0)
        self.assertEqual(agg["overall"]["scored"], 10)
        self.assertEqual(agg["overall"]["rate"], 100.0)

    def test_overall_spans_groups_equally(self):
        rows = _rows(GROUP_APPROVAL, met=10) + _rows(GROUP_ATTENDANCE, missed=10)
        agg = scoring.aggregate(rows, now=D(2026, 9, 16))
        self.assertEqual(agg["overall"]["scored"], 20)
        self.assertEqual(agg["overall"]["rate"], 50.0)

    def test_unknown_group_does_not_crash(self):
        rows = [{"group_key": "nhom_moi", "status": STATUS_MET,
                 "due_at": D(2026, 9, 1), "paused_seconds": 0}]
        agg = scoring.aggregate(rows, now=D(2026, 9, 16))
        self.assertIn("nhom_moi", agg["groups"])

    def test_unknown_group_still_needs_a_sample(self):
        """Mac dinh nguong 0 se lam mot loai nghia vu moi hien 100% tren mot
        dau viec - loi tu quay lai moi lan ai do them mot loai."""
        rows = [{"group_key": "nhom_moi", "status": STATUS_MET,
                 "due_at": D(2026, 9, 1), "paused_seconds": 0}]
        agg = scoring.aggregate(rows, now=D(2026, 9, 16))
        self.assertIsNone(agg["groups"]["nhom_moi"]["rate"])

    def test_unknown_status_is_counted_not_dropped(self):
        rows = [{"group_key": GROUP_APPROVAL, "status": "open",
                 "due_at": D(2026, 9, 1), "paused_seconds": 0}]
        agg = scoring.aggregate(rows, now=D(2026, 9, 16))
        self.assertEqual(agg["groups"][GROUP_APPROVAL]["unknown"], 1)

    def test_row_flag_overrides_constant(self):
        """Co tren TUNG DONG thang hang so. Doi quy tac hom nay khong duoc viet
        lai ti le cua thang truoc."""
        rows = [{"group_key": GROUP_TASK, "status": STATUS_MET,
                 "counts_toward_sla": 1, "due_at": D(2026, 9, 1),
                 "paused_seconds": 0}] * 12
        agg = scoring.aggregate(rows, now=D(2026, 9, 16))
        self.assertEqual(agg["overall"]["scored"], 12)

    def test_empty_month_has_no_rate(self):
        agg = scoring.aggregate([], now=D(2026, 9, 16))
        self.assertIsNone(agg["overall"]["rate"])
        self.assertEqual(agg["overall"]["scored"], 0)


class TestContribution(unittest.TestCase):
    def test_ranks_by_absolute_failures_not_rate(self):
        rows = _rows(GROUP_APPROVAL, met=180, late=20)      # 90%, hong 20
        rows += _rows(GROUP_ATTENDANCE, met=2, missed=2)    # 50%, hong 2
        agg = scoring.aggregate(rows, now=D(2026, 9, 16))
        c = scoring.contribution(agg["groups"])
        self.assertEqual(c[0]["group_key"], GROUP_APPROVAL)
        self.assertEqual(c[0]["fails"], 20)
        self.assertEqual(round(sum(x["share"] for x in c)), 100)

    def test_excludes_non_sla_group(self):
        rows = _rows(GROUP_TASK, missed=50) + _rows(GROUP_APPROVAL, met=10)
        c = scoring.contribution(scoring.aggregate(rows, now=D(2026, 9, 16))["groups"])
        self.assertEqual(c, [])


if __name__ == "__main__":
    unittest.main()
