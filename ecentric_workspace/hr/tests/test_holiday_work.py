# Copyright (c) 2026, eCentric and contributors
"""Danh sach di lam ngay nghi (EC Holiday Work, 24/11/2026).

Boi canh: 24/11 Ngay Van hoa Viet Nam ca cong ty nghi; 23 ban dang ky di lam campaign "tinh nhu
ngay lam binh thuong, thuong 500K + 2 ngay phep". Va 10/10 (thu 7): ca cong ty chi 1 nguoi
cham cong nen ai di lam cung khong xin "Nghi bu OT" duoc ("He thong khong thay ban cham cong").
KHONG can bench: python -m unittest ecentric_workspace.hr.tests.test_holiday_work
"""
import datetime
import importlib
import sys
import types
import unittest

from ecentric_workspace.hr.tests.ss_harness import Doc, FakeFrappe, Thrown, run

TODAY = "2026-11-24"
HW = "`tabEC Holiday Work Member`"


def _d(s):
    return datetime.date(*map(int, str(s)[:10].split("-")))


def _emp_getter(fr, hl="HL-EC"):
    def get_value(dt_, name, field=None, *a, **k):
        if dt_ == "Employee" and isinstance(name, dict):
            return Doc(fr, name="E1", employee_name="A", default_shift="S9", holiday_list=hl,
                       company="eCentric", reports_to=None, lft=1, rgt=2)
        if dt_ == "Shift Type":
            return Doc(fr, name="S9", ec_checkin_cutoff="10:00:00", start_time="09:00:00",
                       begin_check_in_before_shift_start_time=60)
        if dt_ == "Company":
            return "HL-EC"
        if dt_ == "Employee" and field == "holiday_list":
            return hl
        return None
    return get_value


# --------------------------------------------------------------------------- #
# Nghi bu OT (ec_hr_leave_apply)
# --------------------------------------------------------------------------- #
def leave_fr(checkin=False, hw=None):
    """hw: None | (title, allow_comp_off, require_checkin)"""
    fr = FakeFrappe(user="a@x", today=TODAY, form={
        "leave_type": "Compensatory Off", "from_date": "2026-11-26", "to_date": "2026-11-26",
        "ot_date": "2026-10-10", "reason": "Nghi bu campaign"})
    fr.db.get_value = _emp_getter(fr)
    fr.utils.date_diff = lambda a, b: (_d(a) - _d(b)).days
    fr.utils.add_days = lambda d, n: str(_d(d) + datetime.timedelta(days=n))
    fr.on_sql(HW, lambda q, p: [hw] if hw else [])
    fr.on_sql("from `tabEmployee Checkin`", lambda q, p: [(1,)] if checkin else [])
    return fr


class TestNghiBu(unittest.TestCase):
    def test_10_10_khong_cham_cong_co_danh_sach_cho_nghi_bu(self):
        fr = leave_fr(hw=("Campaign 10.10", 1, 0))
        msg = run("ec_hr_leave_apply", fr)
        self.assertEqual(msg["status"], "Open")
        la = [d for d in fr.inserted if d.get("doctype") == "Leave Application"][0]
        self.assertIn("[OT:2026-10-10]", la["description"])

    def test_khong_cham_cong_khong_danh_sach_bao_loi_co_dau(self):
        with self.assertRaises(Thrown) as cm:
            run("ec_hr_leave_apply", leave_fr())
        self.assertIn("Hệ thống không thấy bạn chấm công ngày 10/10/2026", str(cm.exception))
        self.assertIn("danh sách đi làm ngày nghỉ", str(cm.exception))

    def test_dot_khong_cho_nghi_bu_thi_chan_ca_khi_co_cham_cong(self):
        with self.assertRaises(Thrown) as cm:
            run("ec_hr_leave_apply", leave_fr(checkin=True, hw=("Ngày Văn hoá Việt Nam", 0, 1)))
        self.assertIn("không xin nghỉ bù OT được", str(cm.exception))

    def test_dot_bat_cham_cong_ma_khong_cham_thi_van_chan(self):
        with self.assertRaises(Thrown):
            run("ec_hr_leave_apply", leave_fr(hw=("Campaign", 1, 1)))

    def test_co_cham_cong_khong_danh_sach_nhu_cu(self):
        msg = run("ec_hr_leave_apply", leave_fr(checkin=True))
        self.assertEqual(msg["status"], "Open")


# --------------------------------------------------------------------------- #
# Cham cong ngay le cua nguoi trong danh sach (ec_hr_checkin) / trang thai hom nay
# --------------------------------------------------------------------------- #
def checkin_fr(registered):
    fr = FakeFrappe(user="a@x", today=TODAY)
    fr.db.get_value = _emp_getter(fr)
    fr.utils.now_datetime = lambda: datetime.datetime(2026, 11, 24, 8, 40, 0)
    fr.on_sql(HW, lambda q, p: [(1,)] if registered else [])
    fr.on_sql("from `tabHoliday`", lambda q, p: [("Ngày Văn hoá Việt Nam",)])
    return fr


class TestChamCongNgayLe(unittest.TestCase):
    def test_dang_ky_di_lam_thi_ghi_cong(self):
        fr = checkin_fr(True)
        msg = run("ec_hr_checkin", fr)
        self.assertEqual(msg["day_status"], "Present")
        self.assertTrue([d for d in fr.inserted if d.get("doctype") == "Attendance"])

    def test_khong_dang_ky_van_la_ngay_le(self):
        fr = checkin_fr(False)
        msg = run("ec_hr_checkin", fr)
        self.assertEqual(msg["day_status"], "Holiday")
        self.assertFalse([d for d in fr.inserted if d.get("doctype") == "Attendance"])

    def test_today_state(self):
        for reg, want in ((True, 0), (False, 1)):
            fr = FakeFrappe(user="a@x", today=TODAY)
            fr.db.get_value = lambda dt_, name, field=None, *a, **k: (
                "E1" if isinstance(name, dict) else ("HL-EC" if field == "holiday_list" else None))
            fr.on_sql(HW, lambda q, p, reg=reg: [(1,)] if reg else [])
            fr.on_sql("from `tabHoliday`", lambda q, p: [("H",)])
            self.assertEqual(run("ec_hr_today_state", fr)["dayoff"], want)


# --------------------------------------------------------------------------- #
# Python: SLA / nhac cham cong / may khuon mat doc chung lookup
# --------------------------------------------------------------------------- #
class TestDanMa(unittest.TestCase):
    def test_parse_codes(self):
        sys.modules.setdefault("frappe", types.ModuleType("frappe"))
        utils = types.ModuleType("frappe.utils")
        utils.add_days = utils.getdate = utils.nowdate = lambda *a: None
        sys.modules["frappe.utils"] = utils
        sys.modules.pop("ecentric_workspace.hr.holiday_work.service", None)
        svc = importlib.import_module("ecentric_workspace.hr.holiday_work.service")
        self.assertEqual(svc.parse_codes("1\tNV00167\tĐinh Thị Phương Lan\nnv00154, NV00176 x"),
                         ["NV00167", "NV00154", "NV00176"])


class TestSlaLichRieng(unittest.TestCase):
    def test_holidays_for_tru_ngay_dang_ky(self):
        fr = types.ModuleType("frappe")
        fr.get_all = lambda *a, **k: [{"holiday_date": "2026-11-24"}, {"holiday_date": "2026-11-22"}]
        fr.log_error = lambda *a, **k: None
        fr.get_traceback = lambda: ""
        fr.db = types.SimpleNamespace(get_value=lambda *a, **k: "HL-EC")
        utils = types.ModuleType("frappe.utils")
        utils.getdate = _d
        for n in ("get_datetime", "now_datetime", "nowdate", "add_days", "add_to_date", "cint",
                  "flt", "cstr", "time_diff_in_seconds", "date_diff", "now", "today"):
            setattr(utils, n, lambda *a, **k: None)
        utils.getdate = _d
        fr.utils = utils
        fr._ = lambda s, *a: s
        fr.whitelist = lambda *a, **k: (lambda f: f)
        sys.modules["frappe"] = fr
        sys.modules["frappe.utils"] = utils
        lk = types.ModuleType("ecentric_workspace.hr.holiday_work.lookup")
        lk.workday_dates = lambda e, *a: {_d("2026-11-24")} if e == "E1" else set()
        pkg = importlib.import_module("ecentric_workspace.hr.holiday_work")
        real = getattr(pkg, "lookup", None)
        sys.modules["ecentric_workspace.hr.holiday_work.lookup"] = lk
        pkg.lookup = lk
        self.addCleanup(lambda: setattr(pkg, "lookup", real) if real else delattr(pkg, "lookup"))
        for m in ("ecentric_workspace.sla.infrastructure.attendance_source",):
            sys.modules.pop(m, None)
        try:
            att = importlib.import_module("ecentric_workspace.sla.infrastructure.attendance_source")
        except Exception as e:  # module phu thuoc nhieu thu khac cua frappe
            self.skipTest("khong nap duoc attendance_source voi frappe gia: %s" % e)
        cache = {}
        e1 = att._holidays_for({"name": "E1", "holiday_list": "HL-EC"}, cache)
        e2 = att._holidays_for({"name": "E2", "holiday_list": "HL-EC"}, cache)
        self.assertEqual(e1, {_d("2026-11-22")})
        self.assertEqual(e2, {_d("2026-11-22"), _d("2026-11-24")})
        sys.modules.pop("ecentric_workspace.hr.holiday_work.lookup", None)
        sys.modules.pop("ecentric_workspace.sla.infrastructure.attendance_source", None)


if __name__ == "__main__":
    unittest.main()
