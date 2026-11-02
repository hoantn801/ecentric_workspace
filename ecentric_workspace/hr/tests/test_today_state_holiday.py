# Copyright (c) 2026, eCentric and contributors
"""ec_hr_today_state: ho so chua gan lich nghi rieng thi ngay le / cuoi tuan theo lich mac dinh
cua CONG TY van la ngay nghi (dayoff=1) - cung luat voi ec_hr_checkin, ec_hr_attendance_data va
nhac cham cong. Truoc 03/11/2026 script chi doc Employee.holiday_list -> nguoi moi thay thanh
tab bao "chua cham cong" ca T7/CN / ngay le.
python -m unittest ecentric_workspace.hr.tests.test_today_state_holiday"""
import unittest

from ecentric_workspace.hr.tests.ss_harness import FakeFrappe, run

TODAY = "2026-11-07"


def setup(own_hl, company_hl_days, own_hl_days=()):
    fr = FakeFrappe(user="a@x", today=TODAY)
    fr.db.get_value = _gv(fr, own_hl)
    hols = {"HL-EC": set(company_hl_days), "HL-RIENG": set(own_hl_days)}
    fr.on_sql("from `tabHoliday`", lambda q, p: [("H",)] if p[1] in hols.get(p[0], ()) else [])
    return fr


def _gv(fr, own_hl):
    def get_value(dt_, name, field=None, *a, **k):
        if dt_ == "Employee" and isinstance(name, dict):
            return "E1"
        if dt_ == "Employee" and field == "holiday_list":
            return own_hl
        if dt_ == "Employee" and field == "company":
            return "eCentric"
        if dt_ == "Company" and field == "default_holiday_list":
            return "HL-EC" if name == "eCentric" else None
        return None
    return get_value


class TestTodayState(unittest.TestCase):
    def test_khong_lich_rieng_ngay_le_cong_ty_la_ngay_nghi(self):
        msg = run("ec_hr_today_state", setup(None, [TODAY]))
        self.assertEqual(msg["dayoff"], 1)

    def test_lich_rieng_van_uu_tien(self):
        msg = run("ec_hr_today_state", setup("HL-RIENG", [TODAY], []))
        self.assertEqual(msg["dayoff"], 0)

    def test_ngay_thuong_khong_nghi(self):
        msg = run("ec_hr_today_state", setup(None, []))
        self.assertEqual(msg["dayoff"], 0)
        self.assertEqual(msg["checked"], 0)


if __name__ == "__main__":
    unittest.main()
