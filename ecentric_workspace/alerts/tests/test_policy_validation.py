"""Pure unit tests for the shared EC Price Policy validator + CSV row shaping
(Price Setup, 2026-06-14). No frappe - imports the real modules. Covers the
require_complete mode binding (Draft/Paused/Inactive vs Active).

    bench run-tests --module ecentric_workspace.alerts.tests.test_policy_validation
"""
import unittest

from ecentric_workspace.alerts.services import policy_validation as pv
from ecentric_workspace.alerts.services import policy_csv

FULL = {"min_price": 100, "high_alert_percent": 10, "severe_drop_percent": 70}


class TestValidatorDraftMode(unittest.TestCase):
    """require_complete=False (Draft / Paused / Inactive)."""

    def test_missing_all_numerics_is_ok(self):
        self.assertEqual(pv.validate_policy_values({}, require_complete=False), [])
        self.assertEqual(pv.validate_policy_values(
            {"effective_from": "2026-06-01"}, require_complete=False), [])

    def test_present_value_is_range_checked(self):
        self.assertTrue(any("min_price must be > 0" in e for e in
            pv.validate_policy_values({"min_price": 0}, require_complete=False)))
        self.assertTrue(any("min_price must be > 0" in e for e in
            pv.validate_policy_values({"min_price": -5}, require_complete=False)))
        self.assertTrue(any("high_alert_percent" in e for e in
            pv.validate_policy_values({"high_alert_percent": 120}, require_complete=False)))
        self.assertTrue(any("severe_drop_percent" in e for e in
            pv.validate_policy_values({"severe_drop_percent": 0}, require_complete=False)))

    def test_reversed_dates_blocked_in_either_mode(self):
        bad = {"effective_from": "2026-06-10", "effective_to": "2026-06-01"}
        self.assertTrue(pv.validate_policy_values(bad, require_complete=False))
        self.assertTrue(pv.validate_policy_values(bad, require_complete=True))


class TestValidatorActiveMode(unittest.TestCase):
    """require_complete=True (Active / activation)."""

    def test_missing_fields_required_with_fieldnames(self):
        errs = pv.validate_policy_values({"min_price": 100, "high_alert_percent": 10},
                                         require_complete=True)
        self.assertTrue(any("severe_drop_percent" in e and "required" in e for e in errs))
        errs2 = pv.validate_policy_values({}, require_complete=True)
        self.assertTrue(any("min_price is required" in e for e in errs2))
        self.assertTrue(any("high_alert_percent" in e for e in errs2))
        self.assertTrue(any("severe_drop_percent" in e for e in errs2))

    def test_complete_valid_passes(self):
        self.assertEqual(pv.validate_policy_values(FULL, require_complete=True), [])

    def test_percents_independent(self):
        self.assertEqual(pv.validate_policy_values(
            dict(FULL, high_alert_percent=80, severe_drop_percent=5), require_complete=True), [])


class TestCsvRowByStatus(unittest.TestCase):
    """The CSV/paste row goes through policy_csv shape THEN the shared validator
    keyed by the ROW's status - the exact path preview_policy_csv uses."""

    def _eval(self, raw):
        norm, errs = policy_csv.validate_row_shape(raw, 2)
        if errs:
            return errs, None
        errs += pv.validate_policy_values(
            norm, require_complete=((norm.get("status") or "Draft") == "Active"),
            prefix="row 2: ")
        return errs, norm

    def test_draft_row_missing_numerics_ok(self):
        errs, norm = self._eval({"brand": "B", "platform": "Shopee",
                                 "seller_sku": "SKU1", "status": "Draft"})
        self.assertEqual(errs, [])              # Draft: numerics optional
        self.assertIsNotNone(norm)

    def test_active_row_missing_numerics_invalid_fieldlevel(self):
        errs, _ = self._eval({"brand": "B", "platform": "Shopee",
                              "seller_sku": "SKU1", "status": "Active"})
        joined = " ".join(errs)
        self.assertIn("min_price", joined)
        self.assertIn("high_alert_percent", joined)
        self.assertIn("severe_drop_percent", joined)

    def test_draft_row_bad_percent_invalid(self):
        errs, _ = self._eval({"brand": "B", "platform": "Shopee", "seller_sku": "SKU1",
                              "status": "Draft", "high_alert_percent": "120"})
        self.assertTrue(any("high_alert_percent" in e for e in errs))

    def test_identity_fields_required_every_status(self):
        # missing platform -> shape error regardless of status
        errs, _ = self._eval({"brand": "B", "seller_sku": "SKU1", "status": "Draft"})
        self.assertTrue(any("platform" in e for e in errs))


if __name__ == "__main__":
    unittest.main()
