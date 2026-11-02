# -*- coding: utf-8 -*-
"""02/11/2026: nhân viên mới vào /pm được ngay (PM Member tự cấp khi Employee Active có tài khoản).
Ca thật: vi.le (vào 19/10) bị "You do not have access to the PM module". Fake frappe."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _pm_fake as F  # noqa: E402

NEW, OFF, WEB, LEFT = "vi.le@ec.vn", "off@ec.vn", "web@ec.vn", "left@ec.vn"


class TestOnboarding(unittest.TestCase):
    def setUp(self):
        self.fk = F.install()
        F.seed_users(self.fk)
        self.fk.doctypes.add("Role")
        self.fk.add("Role", name="PM Member")
        for u, en, ut in ((NEW, 1, "System User"), (OFF, 0, "System User"), (WEB, 1, "Website User"), (LEFT, 1, "System User")):
            self.fk.add("User", name=u, full_name=u, enabled=en, user_type=ut)
            self.fk.roles[u] = ["Employee"]
        fk = self.fk

        def add_roles(doc, *roles):
            fk.roles.setdefault(doc["name"], [])
            for r in roles:
                if r not in fk.roles[doc["name"]]:
                    fk.roles[doc["name"]].append(r)
        F.FakeDoc.add_roles = add_roles
        self.ob = self.fk.load("ecentric_workspace.pm.onboarding")

    def emp(self, user, status="Active"):
        return F.FakeDoc(self.fk, {"doctype": "Employee", "name": "E-" + user, "user_id": user, "status": status})

    def test_new_active_employee_gets_pm_member(self):
        self.ob.on_employee_update(self.emp(NEW))
        self.assertIn("PM Member", self.fk.roles[NEW])

    def test_idempotent_and_keeps_manager(self):
        self.fk.roles[F.ALICE] = ["PM Manager"]
        self.assertFalse(self.ob.grant_pm_member(F.ALICE))
        self.assertEqual(self.fk.roles[F.ALICE], ["PM Manager"])
        self.ob.on_employee_update(self.emp(NEW)); self.ob.on_employee_update(self.emp(NEW))
        self.assertEqual(self.fk.roles[NEW].count("PM Member"), 1)

    def test_not_for_left_disabled_or_website_users(self):
        self.ob.on_employee_update(self.emp(LEFT, status="Left"))
        self.ob.on_employee_update(self.emp(OFF))
        self.ob.on_employee_update(self.emp(WEB))
        for u in (LEFT, OFF, WEB):
            self.assertNotIn("PM Member", self.fk.roles[u])

    def test_hook_never_raises(self):
        F.FakeDoc.add_roles = lambda *a: (_ for _ in ()).throw(RuntimeError("boom"))
        self.ob.on_employee_update(self.emp(NEW))   # logged, not raised

    def test_backfill_active_only(self):
        self.fk.add("Employee", name="E1", user_id=NEW, status="Active")
        self.fk.add("Employee", name="E2", user_id=LEFT, status="Left")
        real = self.fk.module.get_all   # the shared fake hides Employee from get_all; read it here
        self.fk.module.get_all = lambda dt, **kw: ([r["user_id"] for r in self.fk.db.rows(dt, kw.get("filters"))]
                                                   if dt == "Employee" else real(dt, **kw))
        try:
            self.assertEqual(self.ob.backfill_active_employees(), [NEW])
        finally:
            self.fk.module.get_all = real

    def test_hook_registered_and_patch_listed(self):
        app = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        hooks = open(os.path.join(app, "hooks.py"), encoding="utf-8").read()
        self.assertIn('"ecentric_workspace.pm.onboarding.on_employee_update"', hooks)
        self.assertIn("ecentric_workspace.pm.patches.p030_pm_member_onboarding_backfill",
                      open(os.path.join(app, "patches.txt"), encoding="utf-8").read())


if __name__ == "__main__":
    unittest.main()
