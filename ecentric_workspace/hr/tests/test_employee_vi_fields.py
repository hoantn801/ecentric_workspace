# Copyright (c) 2026, eCentric and contributors
"""Ho ten + chuc danh tieng Viet tren ho so nhan vien (13/10/2026, CnB).

KHONG can bench: python -m unittest ecentric_workspace.hr.tests.test_employee_vi_fields
"""
import importlib
import json
import os
import sys
import types
import unittest

APP = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
NAMES = ("Employee-ec_ho_ten_vi", "Employee-ec_chuc_danh_vi")


def _patch_module():
    sys.modules.setdefault("frappe", types.ModuleType("frappe"))
    return importlib.import_module("ecentric_workspace.hr.patches.p006_ho_ten_chuc_danh_vi")


class TestTruongTiengViet(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(APP, "fixtures", "custom_field.json"), encoding="utf-8") as fh:
            self.rows = {r["name"]: r for r in json.load(fh)}

    def test_hai_truong_nam_canh_ban_tieng_anh(self):
        a, b = self.rows[NAMES[0]], self.rows[NAMES[1]]
        self.assertEqual((a["fieldname"], a["insert_after"], a["fieldtype"]),
                         ("ec_ho_ten_vi", "employee_name", "Data"))
        self.assertEqual((b["fieldname"], b["insert_after"], b["fieldtype"]),
                         ("ec_chuc_danh_vi", "designation", "Data"))

    def test_khong_khoa_sau_permlevel(self):
        # Ho ten / chuc danh khong phai thong tin nhay cam: CnB, HR va chinh nhan vien deu thay.
        for n in NAMES:
            self.assertEqual(self.rows[n]["permlevel"], 0)

    def test_nam_trong_bo_loc_fixture(self):
        with open(os.path.join(APP, "hooks.py"), encoding="utf-8") as fh:
            src = fh.read()
        for n in NAMES:
            self.assertIn('"%s"' % n, src)


class TestCotReport(unittest.TestCase):
    def test_chen_ngay_sau_cot_tieng_anh(self):
        m = _patch_module()
        cols = [["name", "Employee"], ["employee_name", "Employee"], ["department", "Employee"],
                ["designation", "Employee"], ["grade", "Employee"]]
        out = m.add_columns(cols)
        self.assertEqual([c[0] for c in out],
                         ["name", "employee_name", "ec_ho_ten_vi", "department", "designation",
                          "ec_chuc_danh_vi", "grade"])
        self.assertEqual(len(cols), 5)            # khong sua danh sach goc

    def test_chay_lai_khong_them_trung(self):
        m = _patch_module()
        once = m.add_columns([["employee_name", "Employee"], ["designation", "Employee"]])
        self.assertEqual(m.add_columns(once), once)

    def test_report_da_bo_cot_tieng_anh_thi_them_cuoi(self):
        m = _patch_module()
        self.assertEqual(m.add_columns([["name", "Employee"]]),
                         [["name", "Employee"], ["ec_ho_ten_vi", "Employee"],
                          ["ec_chuc_danh_vi", "Employee"]])


if __name__ == "__main__":
    unittest.main()
