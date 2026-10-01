# Copyright (c) 2026, eCentric and contributors
"""Hai cot chot cong tren bang cong HRMS. Python tran, khong can frappe."""
import importlib.util
import io
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TC = os.path.join(HERE, "..", "timesheet_close")
_spec = importlib.util.spec_from_file_location("ec_tsc_report_columns", os.path.join(TC, "report_columns.py"))
RC = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(RC)


def _cols():
    return [{"fieldname": "employee"}, {"fieldname": "employee_name"}, {"fieldname": "shift"},
            {"fieldname": "1"}]


class TestKy(unittest.TestCase):
    def test_thang(self):
        self.assertEqual(RC.period_from_filters({"filter_based_on": "Month", "month": "9", "year": "2026"}), "2026-09")

    def test_khoang_ngay_cung_thang(self):
        self.assertEqual(RC.period_from_filters({"filter_based_on": "Date Range",
                                                 "start_date": "2026-09-01", "end_date": "2026-09-30"}), "2026-09")

    def test_khoang_ngay_hai_thang_thi_khong_them(self):
        self.assertIsNone(RC.period_from_filters({"filter_based_on": "Date Range",
                                                  "start_date": "2026-09-15", "end_date": "2026-10-10"}))


class TestChu(unittest.TestCase):
    def test_chua_chot(self):
        r = {"status": "Open", "lead_user": "lead@x"}
        self.assertEqual(RC.member_text(r), "Chưa chốt")
        self.assertEqual(RC.lead_text(r), "Chưa chốt")

    def test_tu_chot_dung_han(self):
        r = {"status": "Member Closed", "close_mode": "Tu chot", "member_closed_at": "2026-10-01 08:20:16",
             "member_deadline": "2026-10-02 12:00:00", "lead_user": "lead@x"}
        self.assertEqual(RC.member_text(r), "Đã chốt 01/10 08:20")
        self.assertEqual(RC.lead_text(r), "Chưa chốt")

    def test_leader_chot_thay_va_tre(self):
        r = {"status": "Closed", "close_mode": "Leader chot thay", "lead_user": "lead@x",
             "team_closed_at": "2026-10-02 16:00:00", "lead_deadline": "2026-10-02 15:00:00"}
        self.assertEqual(RC.member_text(r), "Leader chốt thay")
        self.assertEqual(RC.lead_text(r), "Đã chốt 02/10 16:00 (trễ)")

    def test_khong_co_lead(self):
        self.assertEqual(RC.lead_text({"status": "Open", "lead_user": None}), "Chưa chốt (CnB/HR)")
        self.assertTrue(RC.lead_text({"status": "Closed", "lead_user": None,
                                      "team_closed_at": "2026-10-02 10:00:00"}).startswith("CnB/HR đã chốt"))

    def test_khong_co_dong_thi_de_trong(self):
        self.assertEqual(RC.member_text(None), "")
        self.assertEqual(RC.lead_text(None), "")


class TestGanCot(unittest.TestCase):
    def test_chen_sau_ten_nhan_vien_va_dien_moi_dong(self):
        data = [{"employee": "E1", "employee_name": "A", "shift": "S1"},
                {"employee": "E1", "employee_name": "A", "shift": "S2"},
                {"department": "Ops"}]
        res = RC.add_columns(([*_cols()], data, "msg", None), {"E1": {"status": "Open", "lead_user": "l"}})
        names = [c["fieldname"] for c in res[0]]
        self.assertEqual(names[:4], ["employee", "employee_name", RC.COL_MEMBER, RC.COL_LEAD])
        self.assertEqual(data[0][RC.COL_MEMBER], "Chưa chốt")
        self.assertEqual(data[1][RC.COL_LEAD], "Chưa chốt")
        self.assertNotIn(RC.COL_MEMBER, data[2])          # dong tieu de nhom
        self.assertEqual(res[2], "msg")                   # giu nguyen message/chart cua HRMS

    def test_khong_co_du_lieu_thi_tra_nguyen(self):
        self.assertEqual(RC.add_columns(([], [], None, None), {}), ([], [], None, None))

    def test_chay_lai_khong_nhan_doi_cot(self):
        cols = _cols()
        res = RC.add_columns((cols, [], None, None), {})
        res2 = RC.add_columns(res, {})
        self.assertEqual([c["fieldname"] for c in res2[0]].count(RC.COL_MEMBER), 1)


class TestNoiDay(unittest.TestCase):
    def test_hooks_dang_ky_lop_report(self):
        with io.open(os.path.join(HERE, "..", "..", "hooks.py"), encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn('"Report", "ecentric_workspace.hr.timesheet_close.report_override.EcReport"', src)

    def test_override_nuot_loi_va_chi_dung_bang_cong(self):
        with io.open(os.path.join(TC, "report_override.py"), encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("super().execute_module(filters)", src)
        self.assertIn("if self.name != RC.REPORT_NAME", src)
        self.assertIn("except Exception", src)


if __name__ == "__main__":
    unittest.main()
