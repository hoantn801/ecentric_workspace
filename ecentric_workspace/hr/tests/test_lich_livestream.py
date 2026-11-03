# Copyright (c) 2026, eCentric and contributors
"""p007 lich livestream: lam ca T7/CN tu ngay ap dung, ngay cu giu nguyen.

KHONG can bench: python -m unittest ecentric_workspace.hr.tests.test_lich_livestream
"""
import importlib
import sys
import types
import unittest

ROWS = [
    {"holiday_date": "2026-09-02", "description": "Quoc khanh", "weekly_off": 0},
    {"holiday_date": "2026-10-31", "description": "Saturday", "weekly_off": 1},
    {"holiday_date": "2026-11-01", "description": "Sunday", "weekly_off": 1},
    {"holiday_date": "2026-11-14", "description": "Saturday", "weekly_off": 1},
    {"holiday_date": "2026-11-15", "description": "Sunday", "weekly_off": 1},
    {"holiday_date": "2026-12-31", "description": "Nghi cuoi nam", "weekly_off": 0},
]


def _mod():
    sys.modules.setdefault("frappe", types.ModuleType("frappe"))
    return importlib.import_module("ecentric_workspace.hr.patches.p007_lich_livestream")


class TestLichLivestream(unittest.TestCase):
    def test_tu_ngay_ap_dung_cuoi_tuan_la_ngay_lam(self):
        days = [r["holiday_date"] for r in _mod().build_rows(ROWS)]
        self.assertNotIn("2026-11-14", days)
        self.assertNotIn("2026-11-15", days)

    def test_ngay_cu_giu_nguyen_de_thang_da_chot_khong_doi(self):
        days = [r["holiday_date"] for r in _mod().build_rows(ROWS)]
        self.assertIn("2026-10-31", days)
        self.assertIn("2026-11-01", days)

    def test_ngay_le_van_nghi(self):
        days = [r["holiday_date"] for r in _mod().build_rows(ROWS)]
        self.assertIn("2026-09-02", days)
        self.assertIn("2026-12-31", days)

    def test_dung_3_ban_truc_livestream(self):
        self.assertEqual(sorted(_mod().USERS), ["an.tran@ecentric.vn", "bao.tran@ecentric.vn",
                                                "sang.bui@ecentric.vn"])


if __name__ == "__main__":
    unittest.main()
