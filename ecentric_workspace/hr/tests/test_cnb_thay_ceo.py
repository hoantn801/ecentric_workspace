# Copyright (c) 2026, eCentric and contributors
"""02/10/2026: CnB / HR duyet THAY CEO giai trinh / don nghi cua nguoi bao cao truc tiep cho
CEO (ec-hr-cnb-thay-ceo-v1). Kiem tren nguon fixtures/server_script.json - KHONG can bench."""
import ast
import io
import json
import os
import unittest

APP = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _scripts():
    with io.open(os.path.join(APP, "fixtures", "server_script.json"), encoding="utf-8") as fh:
        return {r["name"]: r["script"] for r in json.load(fh)}


class ThayCeo(unittest.TestCase):
    def setUp(self):
        self.s = _scripts()

    def test_ba_script_van_hop_le(self):
        for n in ("ec_hr_attendance_data", "ec_hr_leave_data", "ec_hr_leave_decide"):
            ast.parse(self.s[n])
            self.assertIn("ec-hr-cnb-thay-ceo-v1", self.s[n], n)

    def test_danh_sach_cho_duyet_cham_cong_mo_cho_hr_va_bo_viec_cua_chinh_minh(self):
        src = self.s["ec_hr_attendance_data"]
        self.assertIn("appr_mgrs = appr_mgrs + [ceo_emp]", src)
        self.assertEqual(src.count("where e.reports_to in %s and ifnull(e.user_id,'')!=%s"), 2)

    def test_nghi_phep_buoc_lead_hr_thay_ceo_khop_hai_ben(self):
        self.assertIn("thay_ceo = is_hr and mu == CEO_USER", self.s["ec_hr_leave_data"])
        dec = self.s["ec_hr_leave_decide"]
        self.assertIn("thay_ceo = is_hr and mgr_user == CEO_USER", dec)
        self.assertIn("is_admin or thay_ceo):", dec)
        # chot chan tu duyet don cua chinh minh van con
        self.assertIn("Ban khong the tu duyet don nghi cua chinh minh", dec)

    def test_duyet_giai_trinh_hr_von_da_duoc(self):
        for n in ("ec_hr_appeal_decide", "ec_hr_late_decide"):
            self.assertIn("role in ('HR Manager','HR User')", self.s[n], n)


if __name__ == "__main__":
    unittest.main()
