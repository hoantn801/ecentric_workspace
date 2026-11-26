# -*- coding: utf-8 -*-
"""Hotfix 21 (26/11/2026): vi.le không mở được dự án của team (PROJ-0054 không phòng ban).
  P1 tạo dự án không chọn phòng ban -> lấy phòng ban của người tạo.
  P2 chọn phòng ban thì giữ nguyên.
  P3 bị chặn -> câu tiếng Việt có tên dự án + tên quản lý, không còn "Not permitted to view this project"."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _pm_fake as F  # noqa: E402


class T(unittest.TestCase):
    def setUp(self):
        self.fk = F.install()
        F.seed_users(self.fk)
        self.fk.doctypes.add("Employee")
        self.fk.add("Employee", name="EMP-1", user_id=F.ALICE, status="Active", department="Ecom - EC")
        import types
        self.fk.module.defaults = types.SimpleNamespace(get_user_default=lambda k: "eCentric")
        self.pr = self.fk.load("ecentric_workspace.pm.api.projects")
        self.perm = self.fk.load("ecentric_workspace.pm.permissions")

    def test_P1_default_department_of_creator(self):
        self.fk.set_user(F.ALICE)
        r = self.pr.create("AI LIVESTREAM")
        self.assertEqual(self.fk.row("Project", r["name"])["ec_department"], "Ecom - EC")

    def test_P2_explicit_department_kept(self):
        self.fk.set_user(F.ALICE)
        r = self.pr.create("Khac", department="Sales - EC")
        self.assertEqual(self.fk.row("Project", r["name"])["ec_department"], "Sales - EC")

    def test_P3_friendly_message(self):
        self.fk.add("Project", name="PROJ-9", project_name="AI LIVESTREAM", owner=F.GIVER, ec_manager=F.GIVER)
        self.fk.set_user(F.OUTSIDER)
        with self.assertRaises(Exception) as cm:
            self.perm.project_view_scope("PROJ-9", F.OUTSIDER)
        msg = str(cm.exception)
        self.assertIn("AI LIVESTREAM", msg)
        self.assertIn("Gia Ver", msg)
        self.assertNotIn("Not permitted", msg)


if __name__ == "__main__":
    unittest.main()
