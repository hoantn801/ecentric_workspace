# Copyright (c) 2026, eCentric and contributors
"""Test `business_seconds_between` - thuan, chay khong can bench:

    python3 -m unittest ecentric_workspace.approval_center.tests.test_business_seconds -v

Phep kiem quan trong nhat la `test_symmetric_with_due_calculator`: neu do khoang
cach va tinh han khong khop nhau thi "tre 1 gio" va "han 4 gio" khong con cung
mot thuoc do, va moi con so tren bang diem deu sai mot cach khong nhin thay duoc.
Hai ham nay phai la hai chieu cua CUNG mot dinh nghia.
"""
import unittest
from datetime import datetime as D

from ecentric_workspace.approval_center.shared.workflow import business_hours as bh

_ROWS = []
for _wd in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday"):
    _ROWS.append({"weekday": _wd, "start_time": "08:30:00", "end_time": "12:00:00"})
    _ROWS.append({"weekday": _wd, "start_time": "13:30:00", "end_time": "17:30:00"})

P = bh.build_periods(_ROWS)          # 7.5 gio/ngay, T2-T6


class TestBusinessSecondsBetween(unittest.TestCase):
    """16/09/2026 la thu Tu; 18/09 thu Sau; 21/09 thu Hai."""

    def test_within_one_interval(self):
        self.assertEqual(bh.business_seconds_between(
            D(2026, 9, 16, 9, 0), D(2026, 9, 16, 10, 0), P), 3600)

    def test_skips_lunch(self):
        self.assertEqual(bh.business_seconds_between(
            D(2026, 9, 16, 11, 30), D(2026, 9, 16, 14, 0), P), 3600)

    def test_clamps_before_shift(self):
        self.assertEqual(bh.business_seconds_between(
            D(2026, 9, 16, 7, 0), D(2026, 9, 16, 9, 0), P), 1800)

    def test_clamps_after_shift(self):
        self.assertEqual(bh.business_seconds_between(
            D(2026, 9, 16, 17, 0), D(2026, 9, 16, 22, 0), P), 1800)

    def test_full_working_day(self):
        self.assertEqual(bh.business_seconds_between(
            D(2026, 9, 16, 0, 0), D(2026, 9, 17, 0, 0), P), int(7.5 * 3600))

    def test_weekend_costs_nothing(self):
        # 16h thu Sau -> 9h thu Hai = 1.5h + 0.5h. Do bang dong ho se ra 65 gio,
        # va moi cuoi tuan se thanh mot vu tre nghiem trong.
        self.assertEqual(bh.business_seconds_between(
            D(2026, 9, 18, 16, 0), D(2026, 9, 21, 9, 0), P), 7200)

    def test_holiday_costs_nothing(self):
        self.assertEqual(bh.business_seconds_between(
            D(2026, 9, 16, 0, 0), D(2026, 9, 17, 0, 0), P,
            {D(2026, 9, 16).date()}), 0)

    def test_reversed_range_is_zero(self):
        self.assertEqual(bh.business_seconds_between(
            D(2026, 9, 16, 10, 0), D(2026, 9, 16, 9, 0), P), 0)

    def test_empty_calendar_returns_zero_not_raise(self):
        # Khac voi calculate_business_due_at (nem loi khi lich rong, vi "khong
        # bao gio den han" la trang thai khong nuot duoc). O day 0 la con so an
        # toan: khong buoc toi ai vi mot lich cau hinh thieu.
        self.assertEqual(bh.business_seconds_between(
            D(2026, 9, 16, 9, 0), D(2026, 9, 16, 10, 0), {}), 0)

    def test_symmetric_with_due_calculator(self):
        for hours in (1, 4, 7.5, 12, 40):
            for start in (D(2026, 9, 16, 9, 0), D(2026, 9, 18, 16, 0),
                          D(2026, 9, 19, 10, 0), D(2026, 9, 16, 7, 0)):
                due = bh.calculate_business_due_at(start, hours, P)
                self.assertEqual(
                    bh.business_seconds_between(start, due, P), int(hours * 3600),
                    "start=%s hours=%s due=%s" % (start, hours, due))


if __name__ == "__main__":
    unittest.main()
