# Copyright (c) 2026, eCentric and contributors
"""05/10/2026 (ec-team-left-v1): o "Xem lich cong nhan vien" co ca nguoi vua nghi viec de CnB check
cong thang cuoi. Kiem tren nguon fixtures/server_script.json - KHONG can bench."""
import ast
import io
import json
import os
import unittest

APP = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


class TeamMembersLeft(unittest.TestCase):
    def setUp(self):
        with io.open(os.path.join(APP, "fixtures", "server_script.json"), encoding="utf-8") as fh:
            self.s = {r["name"]: r["script"] for r in json.load(fh)}["ec_hr_team_members"]

    def test_hop_le_va_co_marker(self):
        ast.parse(self.s)
        self.assertIn("ec-team-left-v1", self.s)

    def test_ca_hai_nhanh_lay_nguoi_nghi_tu_thang_truoc(self):
        self.assertEqual(self.s.count("(status='Active' or (status!='Active' and relieving_date >= %s))"), 2)
        self.assertIn("add_months(frappe.utils.get_first_day(frappe.utils.nowdate()), -1)", self.s)
        # lead van chi trong nhanh cua minh
        self.assertIn("and lft > %s and rgt < %s", self.s)

    def test_nguoi_nghi_co_nhan_va_xep_cuoi(self):
        self.assertIn("' (nghỉ '", self.s)
        self.assertEqual(self.s.count("order by status='Active' desc, employee_name"), 2)


if __name__ == "__main__":
    unittest.main()
