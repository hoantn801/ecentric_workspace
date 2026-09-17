# Copyright (c) 2026, eCentric and contributors
"""Test luat ngay cong - chay bang python3 tran.

    python3 -m unittest ecentric_workspace.sla.tests.test_attendance_rules -v

Nhom cham cong chiem phan lon mau so cua thang 9 (tinh tu 01/09, ~22 ngay moi
nguoi, trong khi ba nhom kia chi co tu 21/09). Mot luat sai o day khong lam lech
mot nhom - no lam lech %SLA cua ca cong ty trong thang dau tien.
"""
import datetime
import unittest

from ecentric_workspace.sla.domain import attendance_rules as ar

# 01/09/2026 la thu Ba. 05/09 thu Bay, 06/09 Chu nhat, 07/09 thu Hai.
TUE = "2026-09-01"
SAT = "2026-09-05"
SUN = "2026-09-06"
MON = "2026-09-07"
ONTIME = "2026-09-07 08:42:00"


class TestSkipDays(unittest.TestCase):
    def test_weekend_has_no_obligation(self):
        for d in (SAT, SUN):
            act, _, reason = ar.decide(d)
            self.assertEqual(act, ar.ACT_SKIP, d)
            self.assertEqual(reason, ar.REASON_WEEKEND)

    def test_holiday_uses_the_persons_own_list(self):
        act, _, reason = ar.decide(MON, holidays={datetime.date(2026, 9, 7)})
        self.assertEqual((act, reason), (ar.ACT_SKIP, ar.REASON_HOLIDAY))

    def test_someone_elses_holiday_does_not_apply(self):
        act, _, _ = ar.decide(MON, holidays={datetime.date(2026, 9, 8)})
        self.assertEqual(act, ar.ACT_OPEN)

    def test_before_joining_date(self):
        act, _, reason = ar.decide(MON, joined_on="2026-09-10")
        self.assertEqual((act, reason), (ar.ACT_SKIP, ar.REASON_BEFORE_JOIN))

    def test_joining_day_itself_counts(self):
        act, _, _ = ar.decide(MON, joined_on=MON)
        self.assertEqual(act, ar.ACT_OPEN)


class TestLeave(unittest.TestCase):
    def test_approved_leave_is_excluded_not_skipped(self):
        # TAO ban ghi roi loai tru, khong bo han: nguoi ta can nhin thay he thong
        # DA ghi nhan phep cua minh, chu khong phai doan tai sao thang nay thieu
        # mat mot ngay.
        act, _, reason = ar.decide(MON, on_leave=True)
        self.assertEqual((act, reason), (ar.ACT_EXCLUDE, ar.REASON_LEAVE))

    def test_leave_beats_a_checkin(self):
        # Duoc duyet nghi ma van vao lam -> ngay do khong phat sinh nghia vu.
        # Cham "dung han" se cho mot diem mien phi cho ngay khong co nghia vu.
        act, _, reason = ar.decide(MON, on_leave=True, first_checkin=ONTIME)
        self.assertEqual((act, reason), (ar.ACT_EXCLUDE, ar.REASON_LEAVE))

    def test_weekend_beats_leave(self):
        # Khong tao ban ghi "nghi phep" cho Chu nhat - khong ai no gi ngay do.
        act, _, reason = ar.decide(SUN, on_leave=True)
        self.assertEqual((act, reason), (ar.ACT_SKIP, ar.REASON_WEEKEND))


class TestCheckin(unittest.TestCase):
    def test_checked_in_closes_with_that_moment(self):
        act, closed, reason = ar.decide(MON, first_checkin=ONTIME)
        self.assertEqual((act, closed, reason), (ar.ACT_CLOSE, ONTIME, ar.REASON_DONE))

    def test_no_checkin_stays_open(self):
        act, closed, reason = ar.decide(MON)
        self.assertEqual((act, closed, reason), (ar.ACT_OPEN, None, ar.REASON_PENDING))

    def test_late_checkin_still_closes(self):
        # Luat tre/dung han la viec cua scoring.classify_close, khong phai o day.
        # O day chi noi "da cham luc nay".
        act, closed, _ = ar.decide(MON, first_checkin="2026-09-07 10:37:00")
        self.assertEqual(act, ar.ACT_CLOSE)
        self.assertEqual(closed, "2026-09-07 10:37:00")


class TestWorkdaysBetween(unittest.TestCase):
    def test_first_half_of_september(self):
        # 01/09 (T3) den 18/09 (T6): tru hai cuoi tuan 5-6 va 12-13.
        days = ar.workdays_between("2026-09-01", "2026-09-18")
        self.assertEqual(len(days), 14)
        self.assertNotIn(datetime.date(2026, 9, 5), days)
        self.assertNotIn(datetime.date(2026, 9, 13), days)
        self.assertIn(datetime.date(2026, 9, 1), days)
        self.assertIn(datetime.date(2026, 9, 18), days)

    def test_holidays_come_out(self):
        days = ar.workdays_between("2026-09-01", "2026-09-04",
                                   holidays={datetime.date(2026, 9, 2)})
        self.assertEqual(len(days), 3)

    def test_single_day_range(self):
        self.assertEqual(ar.workdays_between(MON, MON), [datetime.date(2026, 9, 7)])
        self.assertEqual(ar.workdays_between(SAT, SAT), [])


class TestInputShapes(unittest.TestCase):
    def test_accepts_date_and_datetime_and_string(self):
        for v in (datetime.date(2026, 9, 7), datetime.datetime(2026, 9, 7, 3, 0),
                  "2026-09-07", "2026-09-07 00:00:00", "2026-09-07T00:00:00"):
            self.assertEqual(ar.decide(v)[0], ar.ACT_OPEN, repr(v))

    def test_no_day_is_skipped_not_crashed(self):
        self.assertEqual(ar.decide(None)[0], ar.ACT_SKIP)


if __name__ == "__main__":
    unittest.main()
