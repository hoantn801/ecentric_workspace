# Copyright (c) 2026, eCentric and contributors
"""Pure tests for the Reports Center visibility gate.
Run WITHOUT a bench:  python3 -m unittest ecentric_workspace.reporting.tests.test_permissions
(frappe is stubbed; is_report_visible never touches the DB)."""
import sys
import types
import unittest

sys.modules.setdefault("frappe", types.ModuleType("frappe"))

from ecentric_workspace.reporting import permissions as P


def ctx(roles=(), depts=(), admin=False):
    return {"user": "u@e.c", "roles": set(roles), "departments": set(depts), "is_admin": admin}


def vis(mode, status="Active", roles=None, depts=None, c=None, inc=False):
    return P.is_report_visible(visibility_mode=mode, card_status=status,
                               allowed_roles=roles or [], allowed_departments=depts or [],
                               ctx=c or ctx(), include_disabled=inc)


class TestReportVisibility(unittest.TestCase):
    def test_admin_sees_everything_except_disabled(self):
        a = ctx(admin=True)
        self.assertTrue(vis("Admin Only", c=a))
        self.assertTrue(vis("Restricted Roles", roles=["X"], c=a))
        self.assertFalse(vis("All Internal Users", status="Disabled", c=a))
        self.assertTrue(vis("All Internal Users", status="Disabled", c=a, inc=True))

    def test_all_internal(self):
        self.assertTrue(vis("All Internal Users", c=ctx()))

    def test_admin_only_hidden_from_normal(self):
        self.assertFalse(vis("Admin Only", c=ctx(roles=["Employee"])))

    def test_disabled_hidden_from_normal(self):
        self.assertFalse(vis("All Internal Users", status="Disabled", c=ctx()))

    def test_restricted_roles(self):
        self.assertTrue(vis("Restricted Roles", roles=["Manager"], c=ctx(roles=["Manager"])))
        self.assertFalse(vis("Restricted Roles", roles=["Manager"], c=ctx(roles=["Employee"])))
        self.assertFalse(vis("Restricted Roles", roles=[], c=ctx(roles=["Manager"])),
                         "empty allow-list = fail-closed")

    def test_restricted_departments(self):
        mgmt = ctx(depts=["Management - EC"])
        self.assertTrue(vis("Restricted Departments", depts=["Management - EC"], c=mgmt))
        self.assertFalse(vis("Restricted Departments", depts=["Management - EC"],
                             c=ctx(depts=["Operation - EC"])))
        self.assertFalse(vis("Restricted Departments", depts=[], c=mgmt),
                         "empty allow-list = fail-closed")

    def test_pnl_seed_case(self):
        # exactly the seeded PnL card: only Management - EC sees it
        mgr = ctx(depts=["Management - EC"])
        other = ctx(depts=["Commercial - EC"], roles=["Employee"])
        self.assertTrue(vis("Restricted Departments", depts=["Management - EC"], c=mgr))
        self.assertFalse(vis("Restricted Departments", depts=["Management - EC"], c=other))

    def test_unknown_mode_fail_closed(self):
        self.assertFalse(vis("Totally Bogus", c=ctx(roles=["Manager"])))


if __name__ == "__main__":
    unittest.main()
