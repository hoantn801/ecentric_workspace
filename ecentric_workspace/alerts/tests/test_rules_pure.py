"""Pure-logic tests for rules / pricing / dedupe_keys - NO frappe required.
Run anywhere:  python -m unittest ecentric_workspace.alerts.tests.test_rules_pure
Covers Phase C cases 4-8 (logic layer) + boundary/edge cases + C1 key formats.
"""
import unittest

from ecentric_workspace.alerts.services import dedupe_keys, pricing, rules

POLICY = {"min_price": 50000, "high_alert_percent": 30, "severe_drop_percent": 70}


class TestRules(unittest.TestCase):
    # case 6: median 99,000 actual 9,900 -> possible_missing_zero
    def test_missing_zero_exact(self):
        hit = rules.evaluate(9900, POLICY, 99000)
        self.assertEqual(hit["rule_code"], "possible_missing_zero")
        self.assertEqual(hit["severity"], "Critical")
        self.assertEqual(hit["recommended_action"], "Stock Safety Lock")
        self.assertEqual(hit["gap_percent"], 90.0)

    def test_missing_zero_band_edges(self):
        # x10 within 15% of baseline 100k -> unit in [8500, 11500]
        self.assertEqual(rules.evaluate(8500, POLICY, 100000)["rule_code"], "possible_missing_zero")
        self.assertEqual(rules.evaluate(9999, POLICY, 100000)["rule_code"], "possible_missing_zero")
        # below band -> not missing_zero, falls to severe_price_drop
        self.assertEqual(rules.evaluate(8400, POLICY, 100000)["rule_code"], "severe_price_drop")
        # x10 above baseline band but unit < baseline -> severe (84% drop)... 11600*10=116000 > 115000
        self.assertEqual(rules.evaluate(11600, POLICY, 100000)["rule_code"], "severe_price_drop")

    # case 7: median 99,000 actual 25,000 @70% -> severe_price_drop
    def test_severe_drop(self):
        hit = rules.evaluate(25000, POLICY, 99000)
        self.assertEqual(hit["rule_code"], "severe_price_drop")
        self.assertEqual(hit["severity"], "Critical")
        # threshold = 29,700; 29,700 itself is NOT below threshold
        self.assertIsNone(rules.evaluate(29700, {"min_price": 1, "severe_drop_percent": 70}, 99000))

    # case 8: line matches missing_zero + severe + below_min -> ONE winner
    def test_priority_missing_zero_wins(self):
        hit = rules.evaluate(9900, POLICY, 99000)  # also <min 50k and <29.7k severe
        self.assertEqual(hit["rule_code"], "possible_missing_zero")

    def test_priority_severe_beats_below_min(self):
        hit = rules.evaluate(25000, POLICY, 99000)  # below min 50k AND severe
        self.assertEqual(hit["rule_code"], "severe_price_drop")

    # case 4: below min but not severe -> below_min only
    def test_below_min_only(self):
        hit = rules.evaluate(45000, POLICY, 99000)  # 45k > 29.7k threshold, < 50k min
        self.assertEqual(hit["rule_code"], "below_min")
        self.assertEqual(hit["severity"], "Critical")
        self.assertEqual(hit["recommended_action"], "Notify Only")

    # case 5: above high -> warning, never lock
    def test_above_high(self):
        hit = rules.evaluate(140000, POLICY, 99000)  # > 99k*1.3=128.7k
        self.assertEqual(hit["rule_code"], "above_high")
        self.assertEqual(hit["severity"], "Warning")
        self.assertEqual(hit["recommended_action"], "Notify Only")
        self.assertNotIn(hit["rule_code"], rules.LOCK_RECOMMENDED_RULES)

    def test_above_high_uses_min_price_without_baseline(self):
        hit = rules.evaluate(70000, POLICY, None)  # > 50k*1.3=65k
        self.assertEqual(hit["rule_code"], "above_high")

    def test_ok_cases(self):
        self.assertIsNone(rules.evaluate(99000, POLICY, 99000))
        self.assertIsNone(rules.evaluate(60000, POLICY, 99000))   # within all bands
        self.assertIsNone(rules.evaluate(0, POLICY, 99000))       # guard
        self.assertIsNone(rules.evaluate(60000, {"min_price": None}, None))  # nothing to check


class TestPricing(unittest.TestCase):
    def test_paid_over_qty_priority(self):
        p, src = pricing.compute_unit_check_price(
            {"customer_paid_price": 198000, "quantity": 2, "list_price": 120000})
        self.assertEqual((p, src), (99000.0, "customer_paid_price/quantity"))

    def test_fallbacks(self):
        p, src = pricing.compute_unit_check_price({"unit_check_price": 88000, "quantity": 0})
        self.assertEqual((p, src), (88000.0, "payload_unit_price"))
        p, src = pricing.compute_unit_check_price(
            {"list_price": 100000, "seller_discount": 20000, "quantity": 2})
        self.assertEqual((p, src), (90000.0, "list_price_minus_seller_discount"))
        p, src = pricing.compute_unit_check_price({"quantity": 1})
        self.assertEqual((p, src), (None, "unresolved"))

    def test_zero_qty_guard(self):
        p, _ = pricing.compute_unit_check_price({"customer_paid_price": 100, "quantity": 0})
        self.assertIsNone(p)  # cannot divide; no unit_check_price/list_price either


class TestDedupeKeys(unittest.TestCase):
    def test_price_key_spec_format(self):
        self.assertEqual(dedupe_keys.price_alert_key("ORD1", "L1", "below_min"),
                         "omisell|ORD1|L1|price|below_min")
        self.assertEqual(dedupe_keys.lock_action_key("ORD1", "L1", "severe_price_drop"),
                         "omisell|ORD1|L1|stock_safety_lock|severe_price_drop")

    def test_missing_policy_keys_c1(self):
        self.assertEqual(
            dedupe_keys.missing_policy_key("BBT-VN", "Shopee", "SHOP1", "SKU-A", "20260607"),
            "omisell|BBT-VN|Shopee|SHOP1|SKU-A|missing_policy|20260607")
        self.assertEqual(
            dedupe_keys.missing_policy_key("BBT-VN", "Shopee", "SHOP1", "SKU-A", "20260607",
                                           external_product_id="998"),
            "omisell|BBT-VN|Shopee|SHOP1|998|SKU-A|missing_policy|20260607")

    def test_missing_brand_mapping_keys_c1(self):
        self.assertEqual(
            dedupe_keys.missing_brand_mapping_key("Shopee", "RAW9", "SKU-A", "20260607"),
            "omisell|Shopee|RAW9|SKU-A|missing_brand_mapping|20260607")
        self.assertEqual(
            dedupe_keys.missing_brand_mapping_key("Shopee", "RAW9", "SKU-A", "20260607",
                                                  external_product_id="998"),
            "omisell|Shopee|RAW9|998|SKU-A|missing_brand_mapping|20260607")

    def test_long_key_fits_140_deterministically(self):
        k1 = dedupe_keys.missing_policy_key("B" * 60, "Shopee", "S" * 60, "K" * 60, "20260607")
        k2 = dedupe_keys.missing_policy_key("B" * 60, "Shopee", "S" * 60, "K" * 60, "20260607")
        self.assertEqual(k1, k2)
        self.assertLessEqual(len(k1), 140)
        self.assertIn("#", k1)


if __name__ == "__main__":
    unittest.main()
