# Copyright (c) 2026, eCentric and contributors
"""Ba thu cua lo B13. KHONG import frappe - doc bang AST va bang van ban.

Ca ba deu la loai hong khong bao gio bao loi: he thong van chay, van tra ve so,
chi la so sai hoac nguoi ta bi ghi nham.
"""
import ast
import io
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SLA = os.path.join(HERE, "..")


def _read(*parts):
    with io.open(os.path.join(SLA, *parts), encoding="utf-8") as fh:
        return fh.read()


class TestNguongTong(unittest.TestCase):
    """Nguong tong da duoc BO. Mot dau viec cung phai ra ti le."""

    def test_overall_min_sample_bang_0(self):
        src = _read("constants.py")
        m = re.search(r"^OVERALL_MIN_SAMPLE\s*=\s*(\d+)", src, re.M)
        self.assertIsNotNone(m, "khong tim thay OVERALL_MIN_SAMPLE")
        self.assertEqual(m.group(1), "0",
                         "nguong tong phai la 0: mot dau viec van la mot dau viec")

    def test_nguong_nhom_van_con(self):
        """Bo nguong TONG khong duoc keo theo bo nguong NHOM: 1/1 = 100% cua mot
        nhom van la mot con so khong dem duoc voi ai."""
        src = _read("constants.py")
        m = re.search(r"^DEFAULT_MIN_SAMPLE\s*=\s*(\d+)", src, re.M)
        self.assertIsNotNone(m)
        self.assertGreater(int(m.group(1)), 0,
                           "nguong mac dinh cua NHOM phai la so duong")


class TestWeeklyThuTuPhanLoai(unittest.TestCase):
    """`truoc_ngay_ap_dung` phai duoc hoi TRUOC `khong_han`.

    Mot ban bao cao cua tuan W33 khong duoc do, nen viec no co han hay khong la
    chuyen khong lien quan. Hoi nguoc thu tu thi 210 ban cu do vao ro canh bao
    `khong_han` va nam do vinh vien - lam ro do thanh nhieu nen, va mot ro canh
    bao day nhieu nen thi khong con ai nhin nua.
    """

    def test_before_start_dung_truoc_khong_han(self):
        src = _read("infrastructure", "weekly_source.py")
        body = src[src.index("def sync_row("):]
        body = body[:body.index("\ndef ")]
        i_before = body.find("before_start")
        i_khong = body.find('report["khong_han"]')
        self.assertNotEqual(i_before, -1, "khong thay before_start trong sync_row")
        self.assertNotEqual(i_khong, -1, "khong thay ro khong_han trong sync_row")
        self.assertLess(i_before, i_khong,
                        "before_start phai duoc hoi TRUOC khi dem vao khong_han")


class TestHookChamCong(unittest.TestCase):
    """Hook chay BEN TRONG giao dich cham cong cua nguoi dung."""

    def _fn(self, src, name):
        for node in ast.parse(src).body:
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return node
        return None

    def test_hook_ton_tai(self):
        self.assertIsNotNone(self._fn(_read("application", "hooks.py"),
                                      "on_employee_checkin"))

    def test_hook_nuot_moi_loi_va_khong_nem_lai(self):
        fn = self._fn(_read("application", "hooks.py"), "on_employee_checkin")
        tries = [n for n in fn.body if isinstance(n, ast.Try)]
        self.assertEqual(len(tries), 1,
                         "than ham phai la DUNG mot khoi try bao tron")
        handlers = tries[0].handlers
        self.assertEqual(len(handlers), 1)
        t = handlers[0].type
        self.assertTrue(isinstance(t, ast.Name) and t.id == "Exception",
                        "phai bat Exception, khong bat hep hon")
        for node in ast.walk(handlers[0]):
            self.assertNotIsInstance(node, ast.Raise,
                                     "khong duoc nem lai: se rollback ca lan cham cong")

    def test_hook_import_muon(self):
        """Import o dau module se lam vo trang cham cong tren mot bench ma module
        SLA chua migrate."""
        fn = self._fn(_read("application", "hooks.py"), "on_employee_checkin")
        imports = [n for n in ast.walk(fn)
                   if isinstance(n, (ast.Import, ast.ImportFrom))]
        self.assertTrue(imports, "attendance_source phai duoc import BEN TRONG ham")

    def test_sync_one_co_savepoint_rieng(self):
        src = _read("infrastructure", "attendance_source.py")
        body = src[src.index("def sync_one("):]
        self.assertIn("savepoint", body)
        self.assertIn("rollback", body)

    def test_sync_one_khong_viet_lai_luat(self):
        """Phai goi lai `_sync_employee` ma job dem dung, khong tu quyet dinh."""
        src = _read("infrastructure", "attendance_source.py")
        body = src[src.index("def sync_one("):]
        self.assertIn("_sync_employee", body)


if __name__ == "__main__":
    unittest.main()
