# -*- coding: utf-8 -*-
"""recurrence.list cho nguoi KHONG phai leader: quy tac cua chinh minh khong duoc bien mat.

Loi cu: lay 200 quy tac moi sua gan nhat cua CA CONG TY roi moi loc theo quyen -> nguoi thuong
co quy tac cu hon (ngoai top 200) se khong thay quy tac cua minh tren /pm. Kem N+1: moi dong mot
lan get_value(owner) + mot lan tinh lai toan bo du an duoc xem. Fake frappe, no bench.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _pm_fake as F  # noqa: E402


class TestRecurrenceListScope(unittest.TestCase):
    def setUp(self):
        self.fk = F.install()
        F.seed_users(self.fk)
        self.fk.doctypes.add("PM Recurrence")
        self.rec = self.fk.load("ecentric_workspace.pm.api.recurrence")
        self.fk.add("PM Recurrence", name="REC-ALICE", owner=F.ALICE, template_subject="Cua Alice",
                    status="Active", frequency="Daily", project=None,
                    modified="2026-01-01 08:00:00")
        for i in range(205):
            self.fk.add("PM Recurrence", name="REC-G%03d" % i, owner=F.GIVER, template_subject="G",
                        status="Active", frequency="Daily", project=None,
                        modified="2026-10-%02d 08:00:00" % (1 + i % 15))

    def test_own_old_rule_still_listed(self):
        self.fk.set_user(F.ALICE)
        rows = self.rec.list()["rows"]
        self.assertEqual([r["name"] for r in rows], ["REC-ALICE"])
        self.assertNotIn("owner", rows[0])          # giu nguyen hinh dang tra ve

    def test_leader_still_capped(self):
        self.fk.set_user(F.LEADER)
        self.assertEqual(len(self.rec.list()["rows"]), 200)


if __name__ == "__main__":
    unittest.main()
