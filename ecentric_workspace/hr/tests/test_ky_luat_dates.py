# Copyright (c) 2026, eCentric and contributors
"""Ky luat - tinh ngay (ham thuan): thoi hieu D123, keo dai 60 ngay D123.2, ngay hop >= 5 ngay
lam viec (bo T7/CN + ngay le), han phan hoi the vang, xoa ky luat D126.

    python3 -m unittest ecentric_workspace.hr.tests.test_ky_luat_dates
"""
import datetime as dt
import unittest

from ecentric_workspace.hr.tests import ky_luat_fake  # noqa: F401  (frappe gia)
from ecentric_workspace.hr.ky_luat import constants as C
from ecentric_workspace.hr.ky_luat.domain import dates as D

d = dt.date


class TestMonths(unittest.TestCase):
    def test_add_months_clamps_end_of_month(self):
        self.assertEqual(D.add_months(d(2026, 8, 31), 6), d(2027, 2, 28))
        self.assertEqual(D.add_months(d(2027, 8, 31), 6), d(2028, 2, 29))      # nam nhuan
        self.assertEqual(D.add_months(d(2026, 11, 15), 3), d(2027, 2, 15))
        self.assertEqual(D.add_months("2026-01-31", 1), d(2026, 2, 28))

    def test_limitation_6_or_12_months(self):
        self.assertEqual(D.limitation_end(d(2026, 5, 10), False), d(2026, 11, 10))
        self.assertEqual(D.limitation_end(d(2026, 5, 10), True), d(2027, 5, 10))


class TestExtension(unittest.TestCase):
    """D123.2: het thoi gian cam ma thoi hieu da het / con < 60 ngay -> keo dai toi block_end + 60."""

    def test_expired_during_block_extends_60_days(self):
        self.assertEqual(D.extend_for_block(d(2026, 6, 1), d(2026, 6, 30)), d(2026, 8, 29))

    def test_less_than_60_days_left_extends(self):
        # het cam 30/06 -> con 01/07..20/08 = 51 ngay < 60 -> 30/06 + 60 = 29/08
        self.assertEqual(D.extend_for_block(d(2026, 8, 20), d(2026, 6, 30)), d(2026, 8, 29))

    def test_exactly_60_days_left_unchanged(self):
        # con 01/07..29/08 = 60 ngay -> giu nguyen
        self.assertEqual(D.extend_for_block(d(2026, 8, 29), d(2026, 6, 30)), d(2026, 8, 29))

    def test_plenty_left_unchanged(self):
        self.assertEqual(D.extend_for_block(d(2026, 12, 31), d(2026, 6, 30)), d(2026, 12, 31))

    def test_effective_limitation_with_leave(self):
        base, end, used = D.effective_limitation(d(2026, 1, 15), False, [(d(2026, 7, 1), d(2026, 7, 20))])
        self.assertEqual(base, d(2026, 7, 15))
        self.assertEqual(end, d(2026, 9, 18))            # 20/07 + 60
        self.assertEqual(used, [(d(2026, 7, 1), d(2026, 7, 20))])

    def test_block_after_expiry_does_not_revive(self):
        base, end, used = D.effective_limitation(d(2026, 1, 15), False, [(d(2026, 8, 1), d(2026, 8, 5))])
        self.assertEqual(end, base)
        self.assertEqual(used, [])

    def test_block_before_violation_ignored(self):
        _b, end, used = D.effective_limitation(d(2026, 3, 1), False, [(d(2026, 1, 1), d(2026, 2, 1))])
        self.assertEqual(end, d(2026, 9, 1))
        self.assertEqual(used, [])

    def test_two_blocks_chain(self):
        # han goc 15/07; nghi 01-20/07 -> 18/09; nghi tiep 01/09-10/09 -> con 11/09..18/09 < 60 -> 09/11
        _b, end, used = D.effective_limitation(
            d(2026, 1, 15), False, [(d(2026, 9, 1), d(2026, 9, 10)), (d(2026, 7, 1), d(2026, 7, 20))])
        self.assertEqual(end, d(2026, 11, 9))
        self.assertEqual(len(used), 2)

    def test_merge_adjacent_periods(self):
        self.assertEqual(D.merge_periods([(d(2026, 7, 1), d(2026, 7, 5)), (d(2026, 7, 6), d(2026, 7, 9)),
                                          (d(2026, 7, 20), d(2026, 7, 21))]),
                         [(d(2026, 7, 1), d(2026, 7, 9)), (d(2026, 7, 20), d(2026, 7, 21))])

    def test_block_covering(self):
        p = [(d(2026, 7, 1), d(2026, 7, 5))]
        self.assertEqual(D.block_covering(d(2026, 7, 5), p), p[0])
        self.assertIsNone(D.block_covering(d(2026, 7, 6), p))


class TestWorkdays(unittest.TestCase):
    def test_earliest_meeting_skips_weekend(self):
        # thong bao thu Hai 23/11 -> 5 ngay LV sau: 24,25,26,27,30 -> 30/11
        self.assertEqual(D.earliest_meeting(d(2026, 11, 23), 5), d(2026, 11, 30))

    def test_earliest_meeting_from_friday(self):
        # thu Sau 27/11 -> 30/11, 1, 2, 3, 4/12 -> 04/12
        self.assertEqual(D.earliest_meeting(d(2026, 11, 27), 5), d(2026, 12, 4))

    def test_earliest_meeting_skips_holiday(self):
        self.assertEqual(D.earliest_meeting(d(2026, 11, 23), 5, {d(2026, 11, 25)}), d(2026, 12, 1))

    def test_reply_due_three_workdays(self):
        self.assertEqual(D.reply_due(d(2026, 11, 26), 3), d(2026, 12, 1))   # Thu -> Fri, Mon, Tue
        self.assertEqual(D.reply_due(d(2026, 11, 23), 3, {d(2026, 11, 24)}), d(2026, 11, 27))

    def test_workdays_between(self):
        self.assertEqual(D.workdays_between(d(2026, 11, 23), d(2026, 11, 30)), 5)

    def test_days_left_and_expired(self):
        self.assertEqual(D.days_left(d(2026, 11, 23), d(2026, 11, 23)), 1)
        self.assertFalse(D.is_expired(d(2026, 11, 23), d(2026, 11, 23)))
        self.assertTrue(D.is_expired(d(2026, 11, 23), d(2026, 11, 24)))
        self.assertEqual(D.days_left(d(2026, 12, 6), d(2026, 11, 23)), 14)


class TestExpunge(unittest.TestCase):
    def test_periods_by_penalty(self):
        self.assertEqual(D.expunge_due(d(2026, 11, 23), C.P_REPRIMAND), d(2027, 2, 23))
        self.assertEqual(D.expunge_due(d(2026, 11, 23), C.P_EXTEND), d(2027, 5, 23))
        self.assertEqual(D.expunge_due(d(2026, 11, 23), C.P_DEMOTE), d(2029, 11, 23))
        self.assertIsNone(D.expunge_due(d(2026, 11, 23), C.P_DISMISS))


if __name__ == "__main__":
    unittest.main()
