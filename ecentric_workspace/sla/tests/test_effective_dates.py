# Copyright (c) 2026, eCentric and contributors
"""Test ranh gioi ngay bat dau ap dung - chay bang python3 tran.

    python3 -m unittest ecentric_workspace.sla.tests.test_effective_dates -v

Mot phep so sanh ngay khong dang mot tep test rieng - TRU KHI lech mot ngay o
day lam ca cong ty mat hoac duoc them dung mot ngay diem, va khong ai doc code
ma phat hien ra. Day dung la truong hop do.
"""
import datetime
import unittest

from ecentric_workspace.sla.domain.effective_dates import is_before_start

ATT = "2026-09-01"
OTHERS = "2026-09-21"


class TestBoundary(unittest.TestCase):
    def test_start_day_itself_is_counted(self):
        # ">=", khong phai ">". Loai ca ngay 21/09 la lech mot ngay cho toan bo
        # cong ty, im lang.
        self.assertFalse(is_before_start("2026-09-21 08:00:00", OTHERS))

    def test_day_before_is_excluded(self):
        self.assertTrue(is_before_start("2026-09-20 23:59:59", OTHERS))

    def test_later_day_is_counted(self):
        self.assertFalse(is_before_start("2026-09-30 17:00:00", OTHERS))

    def test_attendance_covers_the_whole_month(self):
        self.assertFalse(is_before_start("2026-09-01 09:00:00", ATT))
        self.assertFalse(is_before_start("2026-09-16 09:00:00", ATT))
        self.assertTrue(is_before_start("2026-08-31 09:00:00", ATT))

    def test_week_of_14_sep_is_excluded_whole(self):
        # 21/09 la thu Hai -> ranh gioi khong cat ngang tuan bao cao nao.
        for d in ("14", "15", "16", "17", "18", "19", "20"):
            self.assertTrue(is_before_start("2026-09-%s 09:00:00" % d, OTHERS), d)

    def test_week_of_21_sep_is_counted_whole(self):
        for d in ("21", "22", "23", "24", "25", "26"):
            self.assertFalse(is_before_start("2026-09-%s 09:00:00" % d, OTHERS), d)


class TestInputShapes(unittest.TestCase):
    def test_accepts_date_datetime_and_string(self):
        self.assertFalse(is_before_start(datetime.date(2026, 9, 21), OTHERS))
        self.assertFalse(is_before_start(datetime.datetime(2026, 9, 21, 0, 0), OTHERS))
        self.assertFalse(is_before_start("2026-09-21", OTHERS))
        self.assertFalse(is_before_start("2026-09-21T08:00:00", OTHERS))

    def test_effective_from_may_be_a_date_object(self):
        self.assertTrue(is_before_start("2026-09-20", datetime.date(2026, 9, 21)))


class TestFailSafeDirection(unittest.TestCase):
    """Cau hinh thieu -> DO, khong bo qua."""

    def test_no_start_date_means_measure_everything(self):
        self.assertFalse(is_before_start("2020-01-01", None))

    def test_no_opened_at_is_not_excluded(self):
        self.assertFalse(is_before_start(None, OTHERS))


if __name__ == "__main__":
    unittest.main()
