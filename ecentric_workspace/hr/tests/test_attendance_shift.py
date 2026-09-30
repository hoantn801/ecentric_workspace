"""Attendance luon co ca (hr/attendance_shift.py). KHONG can bench:
python -m unittest ecentric_workspace.hr.tests.test_attendance_shift
"""
import ast
import importlib
import os
import sys
import types
import unittest

APP = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def load(default_shift=None, shift_types=("EC Standard 9-18",), boom=False):
    fr = types.ModuleType("frappe")
    fr.logged = []

    def get_value(dt, name, field):
        if boom:
            raise RuntimeError("db down")
        return default_shift
    fr.db = types.SimpleNamespace(get_value=get_value, exists=lambda dt, n: n in shift_types)
    fr.log_error = lambda *a, **k: fr.logged.append(a)
    fr.get_traceback = lambda: "tb"
    sys.modules["frappe"] = fr
    sys.modules.pop("ecentric_workspace.hr.attendance_shift", None)
    return fr, importlib.import_module("ecentric_workspace.hr.attendance_shift")


class Doc(dict):
    __getattr__ = dict.get

    def __setattr__(self, k, v):
        self[k] = v


class CaMacDinh(unittest.TestCase):
    def test_attendance_tu_don_nghi_duoc_gan_ca(self):
        fr, m = load()
        d = Doc(employee="HR-EMP-00087", status="On Leave")
        m.ensure_shift(d)
        self.assertEqual(d.shift, "EC Standard 9-18")

    def test_giu_ca_da_co(self):
        fr, m = load()
        d = Doc(employee="E", shift="Ca dem")
        m.ensure_shift(d)
        self.assertEqual(d.shift, "Ca dem")

    def test_uu_tien_ca_mac_dinh_cua_nhan_vien(self):
        fr, m = load(default_shift="Ca sang", shift_types=("Ca sang", "EC Standard 9-18"))
        d = Doc(employee="E")
        m.ensure_shift(d)
        self.assertEqual(d.shift, "Ca sang")

    def test_loi_khong_lam_hong_duyet_don(self):
        fr, m = load(boom=True)
        d = Doc(employee="E")
        m.ensure_shift(d)          # khong nem loi
        self.assertIsNone(d.shift)
        self.assertEqual(len(fr.logged), 1)

    def test_hook_before_insert_da_dang_ky(self):
        # before_insert chay ca khi HRMS dat flags.ignore_validate (tao Attendance cho don nghi).
        src = open(os.path.join(APP, "hooks.py"), encoding="utf-8").read()
        self.assertIn('doc_events.setdefault("Attendance", {})', src)
        self.assertIn('"ecentric_workspace.hr.attendance_shift.ensure_shift"', src)
        self.assertIn('_att_ev.get("before_insert")', src)
        ast.parse(src)


if __name__ == "__main__":
    unittest.main()
