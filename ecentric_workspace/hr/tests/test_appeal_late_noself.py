# Copyright (c) 2026, eCentric and contributors
"""Khong ai tu DUYET giai trinh cham cong / di muon cua chinh minh - ke ca nguoi mang role HR
(cung nguyen tac ec-lv-noself-v1 cua don nghi). Truoc 03/11/2026 ec_hr_appeal_decide va
ec_hr_late_decide chi kiem "quan ly truc tiep HOAC HR" -> mot HR User tu gui giai trinh roi tu
bam duyet duoc, tu sinh Attendance Present cho minh. Trang /ec-hr/attendance da an don cua
chinh minh khoi danh sach cho duyet; backend gio khop lai. Tu choi (rut don) van duoc.
python -m unittest ecentric_workspace.hr.tests.test_appeal_late_noself"""
import unittest

from ecentric_workspace.hr.tests.ss_harness import Doc, FakeFrappe, Thrown, run


def _base(user, action, applicant, hr):
    fr = FakeFrappe(user=user, form={"name": "X-1", "action": action, "comment": ""})
    fr.values[("Employee", "E1", "reports_to")] = "M1"
    fr.values[("Employee", "M1", "user_id")] = "m@x"
    fr.values[("Employee", "E1", "user_id")] = applicant
    fr.on_sql("from `tabHas Role`", lambda q, p: [(1,)] if hr and p[0] == user else [])
    return fr


def appeal(user, action="approve", applicant="hr@x", hr=True):
    fr = _base(user, action, applicant, hr)
    fr.docs[("Attendance Request", "X-1")] = Doc(
        fr, doctype="Attendance Request", name="X-1", employee="E1", docstatus=0,
        ec_appeal_status="Open")
    return fr


def late(user, action="approve", applicant="hr@x", hr=True):
    fr = _base(user, action, applicant, hr)
    fr.docs[("Attendance", "X-1")] = Doc(
        fr, doctype="Attendance", name="X-1", employee="E1", docstatus=1, ec_late_status="Open")
    return fr


class TestAppealNoSelf(unittest.TestCase):
    def test_hr_khong_tu_duyet_giai_trinh_cua_minh(self):
        fr = appeal("hr@x")
        with self.assertRaises(Thrown):
            run("ec_hr_appeal_decide", fr)
        self.assertEqual(fr.submitted, [])

    def test_hr_tu_rut_giai_trinh_van_duoc(self):
        fr = appeal("hr@x", action="reject")
        self.assertEqual(run("ec_hr_appeal_decide", fr)["status"], "Rejected")

    def test_hr_duyet_cho_nguoi_khac_van_duoc(self):
        fr = appeal("hr@x", applicant="a@x")
        self.assertEqual(run("ec_hr_appeal_decide", fr)["status"], "Approved")
        self.assertEqual(fr.submitted, ["X-1"])

    def test_quan_ly_duyet_van_duoc(self):
        fr = appeal("m@x", applicant="a@x", hr=False)
        self.assertEqual(run("ec_hr_appeal_decide", fr)["status"], "Approved")


class TestLateNoSelf(unittest.TestCase):
    def test_hr_khong_tu_duyet_di_muon_cua_minh(self):
        fr = late("hr@x")
        with self.assertRaises(Thrown):
            run("ec_hr_late_decide", fr)
        self.assertEqual(fr.set_values, [])

    def test_hr_tu_rut_van_duoc(self):
        fr = late("hr@x", action="reject")
        self.assertEqual(run("ec_hr_late_decide", fr)["status"], "Rejected")

    def test_quan_ly_duyet_van_duoc(self):
        fr = late("m@x", applicant="a@x", hr=False)
        self.assertEqual(run("ec_hr_late_decide", fr)["status"], "Approved")

    def test_nguoi_ngoai_van_bi_chan(self):
        fr = late("x@x", applicant="a@x", hr=False)
        with self.assertRaises(Thrown):
            run("ec_hr_late_decide", fr)


if __name__ == "__main__":
    unittest.main()
