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

    def test_present_min_price_is_range_checked(self):
        self.assertTrue(any("min_price must be > 0" in e for e in
            pv.validate_policy_values({"min_price": 0}, require_complete=False)))
        self.assertTrue(any("min_price must be > 0" in e for e in
            pv.validate_policy_values({"min_price": -5}, require_complete=False)))

    def test_positive_out_of_range_percent_still_rejected(self):
        # a genuinely-bad POSITIVE legacy value is still caught (>100).
        self.assertTrue(any("high_alert_percent" in e for e in
            pv.validate_policy_values({"high_alert_percent": 120}, require_complete=False)))
        self.assertTrue(any("severe_drop_percent" in e for e in
            pv.validate_policy_values({"severe_drop_percent": 150}, require_complete=False)))

    def test_reversed_dates_blocked_in_either_mode(self):
        bad = {"effective_from": "2026-06-10", "effective_to": "2026-06-01"}
        self.assertTrue(pv.validate_policy_values(bad, require_complete=False))
        self.assertTrue(pv.validate_policy_values(bad, require_complete=True))


class TestValidatorActiveMode(unittest.TestCase):
    """require_complete=True (Active / activation). RC5: only min_price is required;
    the alert thresholds are Rules-owned and never required here."""

    def test_only_min_price_required(self):
        errs = pv.validate_policy_values({}, require_complete=True)
        self.assertTrue(any("min_price is required" in e for e in errs))
        # the thresholds are NOT required anymore (Rules owns them).
        self.assertFalse(any("high_alert_percent" in e for e in errs))
        self.assertFalse(any("severe_drop_percent" in e for e in errs))

    def test_complete_valid_passes(self):
        self.assertEqual(pv.validate_policy_values(FULL, require_complete=True), [])

    def test_percents_independent(self):
        self.assertEqual(pv.validate_policy_values(
            dict(FULL, high_alert_percent=80, severe_drop_percent=5), require_complete=True), [])


class TestRC5LegacyThresholdCompat(unittest.TestCase):
    """RC5 (2026-06-16): the RC4 Price Setup form no longer submits the alert
    thresholds; legacy policies storing 0/blank must stay save-able and activatable,
    and the engine keeps the only authoritative thresholds (Rules overlay)."""

    def test_create_policy_without_alert_thresholds_ok(self):
        # KAM saves price facts only (no thresholds) -> Draft save must pass.
        self.assertEqual(pv.validate_policy_values(
            {"min_price": 100}, require_complete=False), [])
        # ...and even an immediate activate (only min_price needed) passes.
        self.assertEqual(pv.validate_policy_values(
            {"min_price": 100}, require_complete=True), [])

    def test_edit_legacy_high_alert_zero_ok(self):
        # a legacy doc that stores high_alert_percent=0 stays editable (0 = unset).
        self.assertEqual(pv.validate_policy_values(
            {"min_price": 100, "high_alert_percent": 0}, require_complete=False), [])
        self.assertEqual(pv.validate_policy_values(
            {"min_price": 100, "high_alert_percent": 0}, require_complete=True), [])

    def test_edit_legacy_severe_drop_zero_ok(self):
        self.assertEqual(pv.validate_policy_values(
            {"min_price": 100, "severe_drop_percent": 0}, require_complete=False), [])
        self.assertEqual(pv.validate_policy_values(
            {"min_price": 100, "severe_drop_percent": 0}, require_complete=True), [])

    def test_activate_valid_policy_without_thresholds(self):
        self.assertEqual(pv.validate_policy_values(
            {"min_price": 250}, require_complete=True), [])

    def test_existing_valid_legacy_threshold_values_still_accepted(self):
        # a policy that legitimately stored 80 / 65 keeps validating (not cleared,
        # not rejected) - so re-saving it never trips the range error.
        self.assertEqual(pv.validate_policy_values(
            {"min_price": 100, "high_alert_percent": 80, "severe_drop_percent": 65},
            require_complete=True), [])
        # both blank is also fine (the form omits them entirely).
        self.assertEqual(pv.validate_policy_values(
            {"min_price": 100, "high_alert_percent": "", "severe_drop_percent": None},
            require_complete=True), [])


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

    def test_draft_row_requires_min_price(self):
        # Final simplification: EVERY non-gift CSV row needs min_price at the shape
        # stage (even Draft); target/reference stay optional.
        errs, _norm = self._eval({"brand": "B", "platform": "Shopee",
                                  "seller_sku": "SKU1", "status": "Draft"})
        self.assertTrue(any("min_price is required" in e for e in errs))
        ok, norm = self._eval({"brand": "B", "platform": "Shopee", "seller_sku": "SKU1",
                               "status": "Draft", "min_price": "100"})
        self.assertEqual(ok, [])                # min_price present -> Draft validates
        self.assertIsNotNone(norm)

    def test_active_row_missing_min_price_invalid_fieldlevel(self):
        # RC5: an Active row still requires min_price, but NOT the Rules-owned
        # alert thresholds (those are never required on the policy).
        errs, _ = self._eval({"brand": "B", "platform": "Shopee",
                              "seller_sku": "SKU1", "status": "Active"})
        joined = " ".join(errs)
        self.assertIn("min_price", joined)
        self.assertNotIn("high_alert_percent", joined)
        self.assertNotIn("severe_drop_percent", joined)

    def test_active_row_with_min_price_no_thresholds_ok(self):
        # the RC4 form submits only price facts; an Active row with min_price and
        # no thresholds must validate clean.
        errs, _ = self._eval({"brand": "B", "platform": "Shopee", "seller_sku": "SKU1",
                              "status": "Active", "min_price": "100"})
        self.assertEqual(errs, [])

    def test_csv_ignores_legacy_percent_columns(self):
        # high_alert_percent / severe_drop_percent are no longer CSV columns; a stray
        # value is IGNORED at parse/shape (not parsed, not errored). The row validates
        # on its canonical fields only.
        errs, norm = self._eval({"brand": "B", "platform": "Shopee", "seller_sku": "SKU1",
                                 "status": "Draft", "min_price": "100",
                                 "high_alert_percent": "120"})
        self.assertEqual(errs, [])
        self.assertNotIn("high_alert_percent", norm)

    def test_identity_fields_required_every_status(self):
        # missing platform -> shape error regardless of status
        errs, _ = self._eval({"brand": "B", "seller_sku": "SKU1", "status": "Draft"})
        self.assertTrue(any("platform" in e for e in errs))


class TestDeleteDecision(unittest.TestCase):
    """RC7-A hardened safe-delete contract (pure decision). historical_dependency is
    3-valued: True=has historical deps, False=reliably none, None=unknown (fail closed)."""

    def test_draft_no_historical_dependency_allowed(self):
        self.assertIsNone(pv.delete_decision("Draft", is_admin=False, historical_dependency=False))
        self.assertIsNone(pv.delete_decision(None, is_admin=False, historical_dependency=False))

    def test_draft_with_historical_dependency_rejected(self):
        self.assertEqual(pv.delete_decision("Draft", True, historical_dependency=True),
                         "has_dependents")

    def test_active_with_no_dependency_rejected(self):
        self.assertEqual(pv.delete_decision("Active", True, historical_dependency=False),
                         "active_no_delete")
        self.assertEqual(pv.delete_decision("Active", False, historical_dependency=None),
                         "active_no_delete")

    def test_retired_with_historical_dependency_rejected(self):
        for st in ("Paused", "Inactive", "Expired"):
            self.assertEqual(pv.delete_decision(st, True, historical_dependency=True),
                             "has_dependents", st)

    def test_eligible_retired_by_non_admin_rejected(self):
        for st in ("Paused", "Inactive", "Expired"):
            self.assertEqual(pv.delete_decision(st, False, historical_dependency=False),
                             "admin_only", st)

    def test_eligible_retired_by_system_manager_allowed(self):
        for st in ("Paused", "Inactive", "Expired"):
            self.assertIsNone(pv.delete_decision(st, True, historical_dependency=False), st)

    def test_unknown_dependency_fails_closed(self):
        # unknown/unreliable historical dependency -> rejected for every non-Active status.
        for st in ("Draft", "Paused", "Inactive", "Expired"):
            self.assertEqual(pv.delete_decision(st, True, historical_dependency=None),
                             "dependency_unknown", st)


if __name__ == "__main__":
    unittest.main()
