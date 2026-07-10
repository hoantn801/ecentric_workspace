# Copyright (c) 2026, eCentric and contributors
"""Static/reflection test (Part A): every business-form activation module must use the
shared activation-flag helper and must NOT carry a local copy of the parser.

Source-level (no Frappe import needed), so it runs under bench AND standalone.
"""
import os
import re
import unittest

# authoritative 26 active type-code -> module folder
MODULES = [
    "ai_topup", "outside_work", "data_request", "document_request", "daily_target",
    "system_request", "asset_request", "hr_activity", "employee_referral", "livestream_sample",
    "resignation", "promotion", "lateral_move", "special_bonus", "asset_damage_loss",
    "hiring_request", "leave", "late_early_out", "compensation_leave", "employee_info_update",
    "livestream_supplies", "service_referral", "purchase_request", "payment_request",
    "budget_setting", "affiliate_bonus",
]

AC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
IMPORT_RE = re.compile(
    r"from ecentric_workspace\.approval_center\.services\.activation_flags import .*is_dry_run")


class TestActivationUsesSharedFlags(unittest.TestCase):
    def test_all_26_modules_present(self):
        self.assertEqual(len(MODULES), 26)

    def test_each_module_uses_shared_helper_and_has_no_local_parser(self):
        for m in MODULES:
            path = os.path.join(AC_DIR, m, "activation.py")
            self.assertTrue(os.path.exists(path), "missing activation: " + m)
            with open(path, encoding="utf-8") as fh:
                src = fh.read()
            self.assertRegex(src, IMPORT_RE, m + ": must import shared is_dry_run")
            self.assertNotRegex(src, r"\ndef _dry\(", m + ": must not define a local _dry")
            self.assertNotRegex(src, r"\ndef _truthy\(", m + ": must not define a local _truthy")
            self.assertNotRegex(src, r"\ndef is_dry_run\(", m + ": must not shadow is_dry_run")
            # real-execution mode label is the consistent 'commit'
            self.assertNotIn('else "apply"', src, m + ": real-exec mode should be 'commit'")

    def test_shared_util_exists(self):
        self.assertTrue(os.path.exists(os.path.join(AC_DIR, "services", "activation_flags.py")))


if __name__ == "__main__":
    unittest.main()
