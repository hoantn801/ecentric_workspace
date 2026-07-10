# Copyright (c) 2026, eCentric and contributors
"""Unit tests for the shared activation-flag parser (Part A).

Pure-Python (no Frappe), so it runs under bench AND standalone:
  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_activation_flags
  python -m unittest ecentric_workspace.approval_center.tests.test_activation_flags
"""
import unittest

from ecentric_workspace.approval_center.services.activation_flags import (
    is_truthy, is_explicit_false, is_dry_run)


class TestActivationFlags(unittest.TestCase):
    def test_is_truthy(self):
        for v in [1, "1", True, "true", "True", " TRUE ", "yes", "Yes", "on", "ON"]:
            self.assertTrue(is_truthy(v), v)
        for v in [0, "0", False, "false", "no", "off", "", "  ", None, "banana", 2]:
            self.assertFalse(is_truthy(v), v)

    def test_is_explicit_false(self):
        for v in [0, "0", False, "false", "False", " OFF ", "no", "off"]:
            self.assertTrue(is_explicit_false(v), v)
        for v in [1, "1", True, "true", "yes", "", "  ", None, "banana"]:
            self.assertFalse(is_explicit_false(v), v)

    def test_no_args_is_dry_run(self):
        self.assertTrue(is_dry_run())

    def test_apply_and_commit_trigger_execution(self):
        for v in [1, "1", True, "true", "yes", "on"]:
            self.assertFalse(is_dry_run(apply=v), ("apply", v))
            self.assertFalse(is_dry_run(commit=v), ("commit", v))

    def test_dry_run_false_tokens_trigger_execution(self):
        for v in [0, "0", False, "false", "False", "no", "off"]:
            self.assertFalse(is_dry_run(dry_run=v), ("dry_run", v))

    def test_ambiguous_or_empty_stays_dry(self):
        for v in ["", "  ", None, 1, "1", True, "true", "banana"]:
            self.assertTrue(is_dry_run(dry_run=v), ("ambiguous", v))

    def test_never_crashes_on_string_booleans(self):
        # the whole point: no int("true") anywhere
        for a in ["true", "false", "", "yes", "banana", None]:
            for b in ["true", "false", "", "1", None]:
                is_dry_run(dry_run=a, apply=b)
                is_dry_run(dry_run=a, commit=b)

    def test_precedence_apply_over_dry_run(self):
        # explicit apply wins even if dry_run is truthy
        self.assertFalse(is_dry_run(dry_run=1, apply=1))
        self.assertFalse(is_dry_run(dry_run="true", commit="1"))


if __name__ == "__main__":
    unittest.main()
