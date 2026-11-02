# Copyright (c) 2026, eCentric and contributors
"""ec_hr_leave_decide: don hieu/hi/thai san Nhan su duyet xong buoc cuoi PHAI bao (CC) cho CEO
(ec-lv-cc-ceo-v1, Hoan chot 24/09). Truoc 03/11/2026 dieu kien CC la stage_now == 'done' -
nhung ec_approval_stage tren don khong bao gio duoc ghi 'done' (buoc HR giu nguyen 'hr'), nen
CEO chua tung nhan duoc thong bao nao. Chay that script bang frappe gia (tests/ss_harness.py).
python -m unittest ecentric_workspace.hr.tests.test_leave_decide_cc_ceo"""
import unittest

from ecentric_workspace.hr.tests.ss_harness import Doc, FakeFrappe, run

CEO = "lam.nguyen@ecentric.vn"


def setup(user, stage, mgr_user="m@x", applicant="a@x", hr=True):
    fr = FakeFrappe(user=user, form={"name": "LA-1", "action": "approve"})
    fr.docs[("Leave Application", "LA-1")] = Doc(
        fr, doctype="Leave Application", name="LA-1", employee="E1", employee_name="Nguoi A",
        leave_type="Bereavement Leave", from_date="2026-11-04", to_date="2026-11-06",
        total_leave_days=3, status="Open", docstatus=0, ec_approval_stage=stage,
        leave_approver=user)
    fr.values[("Employee", "E1", "reports_to")] = "M1"
    fr.values[("Employee", "M1", "user_id")] = mgr_user
    fr.values[("Employee", "E1", "user_id")] = applicant
    fr.on_sql("from `tabHas Role` where parent=%s and role in ('HR Manager','HR User')",
              lambda q, p: [(1,)] if hr and p[0] == user else [])
    return fr


class TestCcCeo(unittest.TestCase):
    def test_hr_duyet_buoc_cuoi_thi_ceo_nhan_thong_bao(self):
        fr = setup("hr@x", "hr")
        msg = run("ec_hr_leave_decide", fr)
        self.assertEqual(msg["status"], "Approved")
        self.assertEqual(len(fr.notes_for(CEO)), 1)
        self.assertEqual(len(fr.notes_for("m@x")), 1)
        self.assertEqual(fr.logs, [])

    def test_di_san_buoc_ceo_hr_chot_thi_ceo_van_biet(self):
        fr = setup("hr@x", "ceo")
        run("ec_hr_leave_decide", fr)
        self.assertEqual(len(fr.notes_for(CEO)), 1)

    def test_ceo_tu_chot_thi_khong_tu_bao_minh(self):
        fr = setup(CEO, "ceo", hr=False)
        run("ec_hr_leave_decide", fr)
        self.assertEqual(fr.notes_for(CEO), [])

    def test_phep_thuong_khong_lam_phien_ceo(self):
        fr = setup("m@x", "", hr=False)
        run("ec_hr_leave_decide", fr)
        self.assertEqual(fr.notes_for(CEO), [])

    def test_quan_ly_la_ceo_chi_nhan_mot_thong_bao(self):
        fr = setup("hr@x", "hr", mgr_user=CEO)
        run("ec_hr_leave_decide", fr)
        self.assertEqual(len(fr.notes_for(CEO)), 1)

    def test_buoc_lead_chua_xong_khong_bao_ceo(self):
        fr = setup("m@x", "lead", hr=False)
        msg = run("ec_hr_leave_decide", fr)
        self.assertEqual(msg["stage"], "hr")
        self.assertEqual(fr.notes_for(CEO), [])


if __name__ == "__main__":
    unittest.main()
