"""Moc chot cong thang (hr/timesheet_close/rules.py). KHONG can bench:
python -m unittest ecentric_workspace.hr.tests.test_timesheet_close_rules
"""
import datetime as dt
import importlib.util
import os
import unittest

_p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "timesheet_close", "rules.py")
_s = importlib.util.spec_from_file_location("tc_rules", _p)
R = importlib.util.module_from_spec(_s)
_s.loader.exec_module(R)


class Moc(unittest.TestCase):
    def test_thang_9_2026_chot_thu_6_02_10(self):
        m, l = R.deadlines("2026-09")
        self.assertEqual(m, dt.datetime(2026, 10, 2, 12, 0))
        self.assertEqual(l, dt.datetime(2026, 10, 2, 15, 0))

    def test_ngay_2_thu_7_doi_sang_thu_2_ngay_4(self):
        self.assertEqual(R.close_date("2026-12"), dt.date(2027, 1, 4))   # 02/01/2027 la T7

    def test_ngay_2_chu_nhat_doi_sang_thu_2_ngay_3(self):
        self.assertEqual(R.close_date("2027-04"), dt.date(2027, 5, 3))   # 02/05/2027 la CN

    def test_ngay_le_cung_doi(self):
        # 02/09/2027 (Quoc khanh, T5) va 03/09 nghi bu -> T2 06/09
        hol = [dt.date(2027, 9, 2), dt.date(2027, 9, 3)]
        self.assertEqual(R.close_date("2027-08", hol), dt.date(2027, 9, 6))

    def test_leader_sau_nhan_vien_ba_tieng_cung_ngay(self):
        m, l = R.deadlines("2027-04")
        self.assertEqual((l - m).total_seconds(), 3 * 3600)


class Ky(unittest.TestCase):
    def test_ky_dang_chot_la_thang_truoc(self):
        self.assertEqual(R.prev_period(dt.date(2026, 10, 1)), "2026-09")
        self.assertEqual(R.prev_period(dt.date(2027, 1, 3)), "2026-12")

    def test_cua_so_mo_tu_ngay_1(self):
        self.assertFalse(R.window_open("2026-09", dt.date(2026, 9, 30)))
        self.assertTrue(R.window_open("2026-09", dt.date(2026, 10, 1)))

    def test_khong_ap_dung_hoi_to(self):
        self.assertFalse(R.applies("2026-08"))
        self.assertFalse(R.window_open("2026-08", dt.date(2026, 10, 1)))

    def test_bien_thang(self):
        self.assertEqual(R.period_bounds("2027-02"), (dt.date(2027, 2, 1), dt.date(2027, 2, 28)))
        self.assertEqual(R.period_bounds("2026-12"), (dt.date(2026, 12, 1), dt.date(2026, 12, 31)))


class KhoaTrongServerScript(unittest.TestCase):
    """Chot roi thi ba duong sua cong phai tu choi (ec-tsclose-lock-v1)."""

    def test_ba_script_deu_kiem_khoa(self):
        import json
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "fixtures", "server_script.json")
        rows = {r["name"]: r["script"] for r in json.load(open(p, encoding="utf-8"))}
        for n in ("ec_hr_attendance_appeal", "ec_hr_late_explain", "ec_hr_leave_apply"):
            src = rows[n]
            self.assertIn("ec-tsclose-lock-v1", src, n)
            self.assertIn("`tabEC Timesheet Close`", src, n)
            self.assertIn("'Member Closed','Closed'", src, n)
            compile(src, n, "exec")


class ServerScriptKhongDungTenGachDuoi(unittest.TestCase):
    """Server Script chay trong RestrictedPython: ten bien bat dau bang '_' bi TU CHOI luc
    chay ('"_pm" is an invalid variable name'). 30/09 bien `_pm` trong ec_hr_leave_apply
    lam hong MOI don nghi phep - compile() Python thuong khong bat duoc, nen kiem o day."""

    def test_moi_server_script(self):
        import ast
        import json
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "fixtures", "server_script.json")
        for r in json.load(open(p, encoding="utf-8")):
            t = ast.parse(r["script"])
            bad = {n.id for n in ast.walk(t) if isinstance(n, ast.Name) and n.id.startswith("_")}
            bad |= {n.attr for n in ast.walk(t) if isinstance(n, ast.Attribute) and n.attr.startswith("_")}
            bad |= {a.arg for n in ast.walk(t) if isinstance(n, (ast.FunctionDef, ast.Lambda)) for a in n.args.args if a.arg.startswith("_")}
            self.assertEqual(bad, set(), r["name"])

    def test_compile_restricted_neu_co_thu_vien(self):
        try:
            from RestrictedPython import compile_restricted
        except ImportError:
            self.skipTest("RestrictedPython chua cai (pip install RestrictedPython)")
        import json
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "fixtures", "server_script.json")
        for r in json.load(open(p, encoding="utf-8")):
            compile_restricted(r["script"], r["name"], "exec")

if __name__ == "__main__":
    unittest.main()
