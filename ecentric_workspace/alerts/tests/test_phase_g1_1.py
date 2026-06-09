"""Phase G1.1 tests - COMPONENT-BASED price basis + occurrence/case dedupe +
rule thresholds.

Pure parts (pricing, dedupe_keys) run anywhere. rule_overlay.overlay_params is
pure but its module imports frappe, so a minimal stub is installed first.
Engine Case/Occurrence behavior is frappe/DB-dependent -> bench-pending.
    bench --site <dev-site> run-tests --module ecentric_workspace.alerts.tests.test_phase_g1_1
"""
import sys
import types
import unittest

from ecentric_workspace.alerts.services import pricing, dedupe_keys


def _line(**kw):
    # RSP 300000; component AMOUNTS kept separate (G1.1)
    base = {"quantity": 1, "list_price": 300000,
            "seller_discount_amount": 40000, "seller_voucher_amount": 6000,
            "platform_discount_amount": 14000, "platform_voucher_amount": 0,
            "customer_paid_price": None, "unit_check_price": None}
    base.update(kw)
    return base


def _flags(**kw):
    f = dict(pricing.DEFAULT_FLAGS)
    f.update(kw)
    return f


class TestComponentBasis(unittest.TestCase):
    def test_default_is_seller_funded(self):
        # default flags = seller_discount + seller_voucher, NO platform
        r = pricing.evaluate_components(_line(), None)
        self.assertEqual(r["effective_check_price"], 300000 - 40000 - 6000)  # 254000
        self.assertEqual(r["price_components_used"], "seller_discount+seller_voucher")

    def test_customer_checkout_all_components(self):
        r = pricing.evaluate_components(_line(), _flags(
            include_platform_discount=1, include_platform_voucher=1))
        self.assertEqual(r["effective_check_price"], 300000 - 40000 - 6000 - 14000)  # 240000
        self.assertEqual(r["price_components_used"],
                         "seller_discount+seller_voucher+platform_discount+platform_voucher")

    def test_platform_excluded_equals_seller_funded(self):
        r = pricing.evaluate_components(_line(), _flags(
            include_platform_discount=0, include_platform_voucher=0))
        self.assertEqual(r["effective_check_price"], 254000)

    def test_product_discount_only(self):
        # seller voucher OFF -> only product-level seller discount
        r = pricing.evaluate_components(_line(), _flags(include_seller_voucher=0))
        self.assertEqual(r["effective_check_price"], 300000 - 40000)  # 260000
        self.assertEqual(r["price_components_used"], "seller_discount")

    def test_seller_plus_platform_discount_no_voucher(self):
        r = pricing.evaluate_components(_line(), _flags(include_platform_discount=1))
        self.assertEqual(r["effective_check_price"], 300000 - 40000 - 6000 - 14000)  # 240000

    def test_rsp_only_when_all_off(self):
        r = pricing.evaluate_components(_line(), _flags(
            include_seller_discount=0, include_seller_voucher=0))
        self.assertEqual(r["effective_check_price"], 300000)
        self.assertEqual(r["price_components_used"], "rsp_only")

    def test_customer_paid_override(self):
        r = pricing.evaluate_components(
            _line(customer_paid_price=238000), _flags(use_customer_paid_if_available=1))
        self.assertEqual(r["effective_check_price"], 238000)
        self.assertEqual(r["price_components_used"], "customer_paid")

    def test_customer_paid_ignored_when_absent(self):
        r = pricing.evaluate_components(_line(), _flags(use_customer_paid_if_available=1))
        self.assertEqual(r["effective_check_price"], 254000)  # falls to component calc

    def test_components_are_per_unit(self):
        # Omisell original_price + discount/voucher are PER UNIT -> qty does not
        # change the effective unit price.
        r = pricing.evaluate_components(
            _line(quantity=2, list_price=300000, seller_discount_amount=40000,
                  seller_voucher_amount=0, platform_discount_amount=20000), None)
        self.assertEqual(r["effective_check_price"], 260000)  # 300000 - 40000

    def test_customer_paid_is_line_total_divided(self):
        # customer_paid_price (if ever populated) is a LINE total -> /qty.
        r = pricing.evaluate_components(
            _line(quantity=2, customer_paid_price=480000),
            _flags(use_customer_paid_if_available=1))
        self.assertEqual(r["effective_check_price"], 240000)

    def test_audit_amounts_present(self):
        r = pricing.evaluate_components(_line(), None)
        self.assertEqual(r["rsp_price"], 300000)
        self.assertEqual(r["seller_discount_amount"], 40000)
        self.assertEqual(r["seller_voucher_amount"], 6000)
        self.assertEqual(r["platform_discount_amount"], 14000)
        self.assertEqual(r["platform_voucher_amount"], 0)

    def test_no_rsp_falls_back_to_payload(self):
        r = pricing.evaluate_components(
            {"quantity": 1, "unit_check_price": 99000}, None)
        self.assertEqual(r["effective_check_price"], 99000)
        self.assertEqual(r["price_components_used"], "payload_unit")

    def test_unresolved(self):
        r = pricing.evaluate_components({"quantity": 1}, None)
        self.assertIsNone(r["effective_check_price"])
        self.assertEqual(r["price_components_used"], "unresolved")

    def test_default_flags_constant(self):
        self.assertEqual(pricing.DEFAULT_FLAGS["include_seller_discount"], 1)
        self.assertEqual(pricing.DEFAULT_FLAGS["include_seller_voucher"], 1)
        self.assertEqual(pricing.DEFAULT_FLAGS["include_platform_discount"], 0)
        self.assertEqual(pricing.DEFAULT_FLAGS["include_platform_voucher"], 0)

    def test_legacy_compute_unchanged(self):
        p, src = pricing.compute_unit_check_price(
            {"customer_paid_price": 100, "quantity": 1})
        self.assertEqual(p, 100)


class TestOccurrenceKey(unittest.TestCase):
    def test_per_order_line_rule(self):
        k1 = dedupe_keys.occurrence_key("ORD1", "P1:SKUA", "below_min")
        self.assertNotEqual(k1, dedupe_keys.occurrence_key("ORD2", "P1:SKUA", "below_min"))
        self.assertNotEqual(k1, dedupe_keys.occurrence_key("ORD1", "P1:SKUB", "below_min"))
        self.assertEqual(k1, dedupe_keys.occurrence_key("ORD1", "P1:SKUA", "below_min"))
        self.assertIn("occ", k1)
        self.assertLessEqual(len(k1), 140)

    def test_distinct_from_price_alert_key(self):
        self.assertNotEqual(
            dedupe_keys.occurrence_key("O", "L", "below_min"),
            dedupe_keys.price_alert_key("O", "L", "below_min"))


def _stub_frappe():
    try:
        import frappe  # noqa
        return
    except Exception:
        pass
    f = types.ModuleType("frappe")
    f.get_all = lambda *a, **k: []
    f.log_error = lambda *a, **k: None
    sys.modules["frappe"] = f
    sys.modules["frappe.utils"] = types.SimpleNamespace(nowdate=lambda: "2026-06-08")


class TestRuleOwnsThresholds(unittest.TestCase):
    def test_overlay_prefers_rule_fields(self):
        _stub_frappe()
        from ecentric_workspace.alerts.services import rule_overlay
        params = {"min_price": 50000, "high_alert_percent": 30, "severe_drop_percent": 70}
        rmap = {"severe_price_drop": {"rule_code": "severe_price_drop",
                                      "severe_drop_percent": 55, "threshold_percent": None},
                "above_high": {"rule_code": "above_high",
                               "high_alert_percent": 12, "threshold_percent": None}}
        out = rule_overlay.overlay_params(params, rmap)
        self.assertEqual(out["severe_drop_percent"], 55.0)
        self.assertEqual(out["high_alert_percent"], 12.0)

    def test_empty_rules_identity(self):
        _stub_frappe()
        from ecentric_workspace.alerts.services import rule_overlay
        params = {"min_price": 50000, "high_alert_percent": 30, "severe_drop_percent": 70}
        self.assertEqual(rule_overlay.overlay_params(params, {}), params)


if __name__ == "__main__":
    unittest.main()
