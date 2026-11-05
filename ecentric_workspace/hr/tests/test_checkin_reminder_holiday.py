# Copyright (c) 2026, eCentric and contributors
"""Nhac cham cong (hr/checkin_reminder.py) phai nghi theo lich mac dinh cua CONG TY khi ho so
chua gan lich rieng (holiday_list trong). Truoc 03/11/2026 `_should_skip` chi doc
Employee.holiday_list -> nguoi moi chua duoc gan lich bi nhac "chua cham cong" ca T7/CN va
ngay le, trong khi ec_hr_checkin / SLA cham cong deu da lui ve lich cong ty.
frappe gia, KHONG can bench:
python -m unittest ecentric_workspace.hr.tests.test_checkin_reminder_holiday"""
import importlib
import sys
import types
import unittest

TODAY = "2026-11-07"   # thu Bay


def make(holidays, company_hl="HL-EC", leaves=(), checkins=()):
    """holidays: {holiday_list: set(ngay)}"""
    fr = types.ModuleType("frappe")
    fr.conf = {}
    fr.sent = []

    def exists(dt_, filters=None):
        if dt_ == "Holiday":
            return filters["holiday_date"] in holidays.get(filters["parent"], set())
        if dt_ == "Leave Application":
            return filters["employee"] in leaves
        return False

    def get_value(dt_, name, field, *a, **k):
        if dt_ == "Company" and field == "default_holiday_list":
            return company_hl if name == "eCentric" else None
        return None

    def sql(q, params=None, *a, **k):
        if "Employee Checkin" in q:
            return [("CI",)] if params[0] in checkins else []
        return []

    fr.db = types.SimpleNamespace(exists=exists, get_value=get_value, sql=sql)
    fr.whitelist = lambda **k: (lambda f: f)
    fr._ = lambda s: s
    fr.log_error = lambda *a, **k: None
    utils = types.ModuleType("frappe.utils")
    utils.nowdate = lambda: TODAY
    fr.utils = utils
    sys.modules["frappe"] = fr
    sys.modules["frappe.utils"] = utils
    ev = types.ModuleType("ecentric_workspace.notification_center.events")
    ev.publish_notification_event = lambda **k: fr.sent.append(k)
    sys.modules["ecentric_workspace.notification_center.events"] = ev
    fc = types.ModuleType("ecentric_workspace.hr.full_cong")
    fc.is_full_cong = lambda name: False
    sys.modules["ecentric_workspace.hr.full_cong"] = fc
    sys.modules.pop("ecentric_workspace.hr.checkin_reminder", None)
    return importlib.import_module("ecentric_workspace.hr.checkin_reminder")


def emp(name="E1", hl=None, company="eCentric"):
    return {"name": name, "employee_name": name, "user_id": name.lower() + "@x",
            "holiday_list": hl, "date_of_joining": "2026-10-01", "company": company}


class TestLichNghiCongTy(unittest.TestCase):
    def tearDown(self):
        for m in ("frappe", "frappe.utils", "ecentric_workspace.notification_center.events",
                  "ecentric_workspace.hr.full_cong", "ecentric_workspace.hr.checkin_reminder"):
            sys.modules.pop(m, None)

    def test_khong_lich_rieng_thi_theo_lich_cong_ty(self):
        cr = make({"HL-EC": {TODAY}})
        self.assertTrue(cr._should_skip(emp(hl=None), TODAY))

    def test_lich_rieng_van_uu_tien(self):
        # lich rieng KHONG nghi hom nay -> van nhac, du lich cong ty nghi
        cr = make({"HL-EC": {TODAY}, "HL-RIENG": set()})
        self.assertFalse(cr._should_skip(emp(hl="HL-RIENG"), TODAY))

    def test_ngay_lam_viec_van_nhac(self):
        cr = make({"HL-EC": set()})
        self.assertFalse(cr._should_skip(emp(hl=None), TODAY))

    def test_khong_cong_ty_khong_lich_thi_van_nhac(self):
        cr = make({"HL-EC": {TODAY}})
        self.assertFalse(cr._should_skip(emp(hl=None, company=None), TODAY))

    def test_truy_van_nhan_vien_lay_ca_company(self):
        import io
        import os
        src = io.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                                   "checkin_reminder.py"), encoding="utf-8").read()
        self.assertEqual(src.count('"holiday_list", "date_of_joining", "company"]'), 2)


if __name__ == "__main__":
    unittest.main()
