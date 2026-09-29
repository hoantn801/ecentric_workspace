# Copyright (c) 2026, eCentric and contributors
"""The Nhan su (/tong-quan): phan dung du lieu thuan Python, KHONG can bench.

Canh cac bat bien quan trong: nguoi khong co permlevel 1 thi khong bi lo 'co/khong co'
du lieu ca nhan; khong co hop dong khi khong co permlevel 2; CCCD/STK luon bi che;
khong co truong luong nao lot ra."""
import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from ecentric_workspace.hr.overview import constants as C  # noqa: E402
from ecentric_workspace.hr.overview.profile_service import GetHrProfileService, mask  # noqa: E402
from ecentric_workspace.hr.overview.service import BuildHrOverviewService  # noqa: E402

TODAY = datetime.date(2026, 9, 28)


def emp(name, **kw):
    base = {"name": name, "employee_name": name.upper(), "department": "Production - EC",
            "ec_sub_department": "Design", "designation": "X", "grade": "Nhân viên",
            "reports_to": "BOSS", "user_id": name + "@x", "employment_type": "Full-time",
            "cell_number": "090", "date_of_birth": "2000-01-01", "passport_number": "012345678901",
            "bank_ac_no": "123456789", "health_insurance_no": "79"}
    base.update(kw)
    return base


BOSS = emp("BOSS", department="Management - EC", grade="Trưởng phòng", reports_to=None,
           user_id="boss@x", ec_sub_department=None)
DEPTS = [{"name": "Production - EC", "manager_email": "boss@x"},
         {"name": "Service - EC", "manager_email": "staff@x"},
         {"name": "Management - EC", "manager_email": "boss@x"}]


class TestOverview(unittest.TestCase):
    def build(self, emps, cons=(), levels=(0, 1, 2), mem=()):
        return BuildHrOverviewService().execute(list(emps), list(cons), DEPTS, list(mem), set(levels), TODAY)

    def test_contract_and_probation_windows(self):
        cons = [{"parent": "A", "loai_hop_dong": "HĐLĐ lần 1", "tu_ngay": "2025-10-01", "den_ngay": "2026-10-10"},
                {"parent": "A", "loai_hop_dong": "Thử việc", "tu_ngay": "2025-08-01", "den_ngay": "2025-09-30"},
                {"parent": "B", "loai_hop_dong": "Thử việc", "tu_ngay": "2026-08-01", "den_ngay": "2026-10-05"},
                {"parent": "C", "loai_hop_dong": "HĐLĐ lần 2", "tu_ngay": "2026-01-01", "den_ngay": None, "khong_thoi_han": 1}]
        d = self.build([BOSS, emp("A"), emp("B"), emp("C")], cons)
        rows = {r["name"]: r for r in d["directory"]}
        self.assertTrue(rows["A"]["contract_warn"])            # hop dong MOI NHAT, con 12 ngay
        self.assertFalse(rows["A"]["probation_warn"])
        self.assertTrue(rows["B"]["probation_warn"])
        self.assertFalse(rows["C"]["contract_warn"])           # KXD khong bao gio canh bao
        self.assertEqual(d["stats"]["contract_warn"], 1)
        self.assertEqual(d["stats"]["probation_warn"], 1)
        self.assertEqual(d["todo"][0]["row"], "B")              # gan han nhat len dau

    def test_without_l1_personal_fields_are_not_even_checked(self):
        e = emp("A", cell_number=None, passport_number=None, bank_ac_no=None)
        full = self.build([BOSS, e])
        dir_only = self.build([BOSS, {k: v for k, v in e.items() if k not in C.L1_FIELDS}], levels=(0, 2))
        a_full = [r for r in full["directory"] if r["name"] == "A"][0]
        a_l0 = [r for r in dir_only["directory"] if r["name"] == "A"][0]
        self.assertIn("CCCD", a_full["missing"])
        self.assertEqual(a_l0["missing"], [])
        self.assertFalse(dir_only["checks_personal"])

    def test_without_l2_no_contract_info(self):
        cons = [{"parent": "A", "loai_hop_dong": "Thử việc", "tu_ngay": "2026-08-01", "den_ngay": "2026-10-01"}]
        d = self.build([BOSS, emp("A")], cons, levels=(0,))
        self.assertFalse(d["has_contracts"])
        self.assertEqual(d["directory"][1]["contract_type"], "")
        self.assertEqual(d["stats"]["probation_warn"], 0)

    def test_head_must_be_head_grade(self):
        staff = emp("S", department="Service - EC", user_id="staff@x", ec_sub_department="Affiliate")
        d = self.build([BOSS, emp("A"), staff])
        org = {o["department"]: o for o in d["org"]}
        self.assertTrue(org["Production - EC"]["head_ok"])
        self.assertFalse(org["Service - EC"]["head_ok"])        # manager_email la nhan vien
        self.assertTrue(org["Management - EC"]["is_management"])
        self.assertEqual(d["org"][-1]["department"], "Management - EC")

    def test_bod_needs_no_manager(self):
        d = self.build([emp("L", grade="BOD", reports_to=None)])
        self.assertNotIn("Người quản lý", d["directory"][0]["missing"])

    def test_no_salary_field_anywhere(self):
        for f in C.L0_FIELDS + C.L1_FIELDS + C.L2_FIELDS:
            self.assertNotIn(f, ("ctc", "base", "gross_pay", "net_pay", "ec_allow_coffee",
                                 "ec_allow_lunch", "ec_allow_computer"))


class TestProfile(unittest.TestCase):
    def test_mask_and_levels(self):
        e = emp("A")
        full = GetHrProfileService().execute(e, [], {0, 1, 2}, "Boss")
        cccd = [p for p in full["personal"] if p["label"] == "CCCD"][0]["value"]
        self.assertEqual(cccd, "•••• 8901")
        self.assertNotIn("012345678901", str(full))
        hr_user = GetHrProfileService().execute({k: v for k, v in e.items() if k not in C.L1_FIELDS}, [], {0, 2})
        self.assertNotIn("personal", hr_user)
        self.assertIn("contracts", hr_user)
        l0 = GetHrProfileService().execute({k: v for k, v in e.items() if k not in C.L1_FIELDS}, [], {0})
        self.assertNotIn("contracts", l0)

    def test_mask_short(self):
        self.assertEqual(mask("12"), "••••")
        self.assertEqual(mask(None), "")


if __name__ == "__main__":
    unittest.main()
