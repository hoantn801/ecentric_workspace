"""Phase F M1 tests. Pure classes run anywhere; Bench classes need a site:
    bench --site <dev-site> run-tests --module ecentric_workspace.alerts.tests.test_phase_f
"""
import json
import unittest

import frappe

from ecentric_workspace.alerts.services import policy_csv, rule_overlay, rules

POLICY = {"min_price": 50000, "high_alert_percent": 30, "severe_drop_percent": 70}


def _row(**kw):
    base = {"name": "EC-AR-1", "rule_code": "below_min", "platform": None,
            "shop": None, "item": None, "seller_sku": None,
            "severity_override": None, "threshold_percent": None,
            "recommend_stock_lock": 0, "effective_from": None, "effective_to": None}
    base.update(kw)
    return base


class TestOverlayGolden(unittest.TestCase):
    """THE guarantee: no Active rule rows -> byte-identical behavior."""

    def test_empty_rules_map_is_identity(self):
        for price, base in ((9900, 99000), (25000, 99000), (45000, 99000),
                            (140000, 99000), (99000, 99000), (60000, None)):
            params = dict(POLICY)
            self.assertEqual(rule_overlay.overlay_params(params, {}), params)
            hit = rules.evaluate(price, params, base)
            self.assertEqual(rule_overlay.overlay_hit(hit, {}), hit)
        for code in ("possible_missing_zero", "severe_price_drop"):
            self.assertTrue(rule_overlay.lock_narrowing(code, {}))
        for code in ("below_min", "above_high", "missing_policy"):
            self.assertFalse(rule_overlay.lock_narrowing(code, {}))


class TestOverlayBehavior(unittest.TestCase):
    def test_severity_override(self):
        hit = rules.evaluate(45000, POLICY, 99000)          # below_min Critical
        out = rule_overlay.overlay_hit(hit, {"below_min": _row(severity_override="Warning")})
        self.assertEqual(out["severity"], "Warning")
        self.assertEqual(hit["severity"], "Critical")        # input not mutated

    def test_below_min_escalation(self):
        rmap = {"below_min": _row(threshold_percent=20)}
        # gap 10% (45k vs 50k) -> below threshold -> Warning
        hit = rules.evaluate(45000, {"min_price": 50000}, None)
        self.assertEqual(rule_overlay.overlay_hit(hit, rmap)["severity"], "Warning")
        # gap 40% (30k vs 50k) -> >= 20% -> Critical
        hit2 = rules.evaluate(30000, {"min_price": 50000}, None)
        self.assertEqual(rule_overlay.overlay_hit(hit2, rmap)["severity"], "Critical")

    def test_threshold_params(self):
        out = rule_overlay.overlay_params(dict(POLICY), {
            "severe_price_drop": _row(rule_code="severe_price_drop", threshold_percent=50),
            "above_high": _row(rule_code="above_high", threshold_percent=10)})
        self.assertEqual(out["severe_drop_percent"], 50.0)
        self.assertEqual(out["high_alert_percent"], 10.0)
        self.assertEqual(out["min_price"], 50000)            # untouched

    def test_lock_narrowing_never_widens(self):
        # config CANNOT make below_min/above_high lockable
        rmap = {"below_min": _row(recommend_stock_lock=1)}
        self.assertFalse(rule_overlay.lock_narrowing("below_min", rmap))
        # explicit disable narrows a lockable rule
        rmap2 = {"severe_price_drop": _row(rule_code="severe_price_drop",
                                           recommend_stock_lock=0)}
        self.assertFalse(rule_overlay.lock_narrowing("severe_price_drop", rmap2))
        rmap3 = {"severe_price_drop": _row(rule_code="severe_price_drop",
                                           recommend_stock_lock=1)}
        self.assertTrue(rule_overlay.lock_narrowing("severe_price_drop", rmap3))

    def test_match_score_priority(self):
        # SKU(8) > shop(4) > platform(2) > brand(1)
        s_brand = rule_overlay._match_score(frappe._dict(_row()), "Shopee", "S1", None, "SKU1")
        s_plat = rule_overlay._match_score(frappe._dict(_row(platform="Shopee")), "Shopee", "S1", None, "SKU1")
        s_shop = rule_overlay._match_score(frappe._dict(_row(shop="S1")), "Shopee", "S1", None, "SKU1")
        s_sku = rule_overlay._match_score(frappe._dict(_row(seller_sku="SKU1")), "Shopee", "S1", None, "SKU1")
        self.assertTrue(s_brand < s_plat < s_shop < s_sku)
        self.assertIsNone(rule_overlay._match_score(
            frappe._dict(_row(seller_sku="OTHER")), "Shopee", "S1", None, "SKU1"))


class TestPolicyCsv(unittest.TestCase):
    def test_template_no_shop_has_is_gift(self):
        hdr = policy_csv.template_csv().split("\n")[0].split(",")
        self.assertNotIn("shop", hdr)
        self.assertIn("is_gift", hdr)

    def test_template_and_roundtrip(self):
        t = policy_csv.template_csv()
        rows, errs, warns = policy_csv.parse_csv(
            t + "FES-VN,Shopee,SKU-A,,Prod A,5.000.000,,,,70,1,2026-06-01,,Active,\n")
        self.assertEqual(errs, [])
        self.assertEqual(warns, [])
        norm, rerr = policy_csv.validate_row_shape(rows[0], 2)
        self.assertEqual(rerr, [])
        self.assertEqual(norm["min_price"], 5000000.0)       # vi-VN dots survive
        self.assertEqual(norm["enable_stock_safety_lock"], 1)
        self.assertFalse(norm["is_gift"])

    def test_old_file_with_shop_still_parses_and_warns(self):
        body = "brand,platform,shop,seller_sku,status\nFES-VN,Shopee,SHOP-X,SKU-A,Draft\n"
        rows, errs, warns = policy_csv.parse_csv(body)
        self.assertEqual(errs, [])
        self.assertTrue(any("SHOP is deprecated" in w for w in warns))
        self.assertNotIn("shop", rows[0])                    # value dropped at parse
        norm, rerr = policy_csv.validate_row_shape(rows[0], 2)
        self.assertEqual(rerr, [])
        self.assertNotIn("shop", norm)                       # never persisted

    def test_gift_value_variants(self):
        for v in ("YES", "yes", "TRUE", "true", "1", "Y", "y"):
            self.assertTrue(policy_csv.is_gift_value(v), v)
        for v in ("", "NO", "no", "0", "false", "x"):
            self.assertFalse(policy_csv.is_gift_value(v), v)

    def test_gift_row_requires_sku_ignores_price(self):
        norm, errs = policy_csv.validate_row_shape(
            {"brand": "B", "platform": "Shopee", "seller_sku": "G1", "is_gift": "YES"}, 2)
        self.assertEqual(errs, [])
        self.assertTrue(norm["is_gift"])
        self.assertNotIn("min_price", norm)                  # prices ignored on gift rows
        norm2, errs2 = policy_csv.validate_row_shape(
            {"brand": "B", "platform": "Shopee", "is_gift": "YES"}, 3)
        self.assertIsNone(norm2)
        self.assertTrue(any("seller_sku" in e for e in errs2))

    def test_two_rows_differ_only_by_shop_same_shape(self):
        a, _ = policy_csv.validate_row_shape({"brand": "B", "platform": "Shopee", "seller_sku": "S1", "shop": "X"}, 2)
        b, _ = policy_csv.validate_row_shape({"brand": "B", "platform": "Shopee", "seller_sku": "S1", "shop": "Y"}, 3)
        self.assertEqual(a, b)                               # shop ignored -> identical row

    def test_rejections(self):
        rows, errs, warns = policy_csv.parse_csv("foo,bar\n1,2\n")
        self.assertTrue(errs and "unknown columns" in errs[0])
        bad = {"brand": "", "platform": "Shoppee", "min_price": "abc",
               "seller_sku": "", "item": "", "status": "Weird"}
        norm, rerr = policy_csv.validate_row_shape(bad, 2)
        self.assertIsNone(norm)
        self.assertEqual(len(rerr), 5)  # brand req, platform, min_price NaN, sku/item, status

    def test_row_cap(self):
        body = policy_csv.template_csv() + "\n".join(
            "FES-VN,Shopee,S%d,,,1000,,,,,0,,,Draft," % i for i in range(501)) + "\n"
        rows, errs, warns = policy_csv.parse_csv(body)
        self.assertTrue(errs and "too many rows" in errs[0])


class TestPermissionsF(unittest.TestCase):
    """Mock-level capability matrix for the 3 new functions (full matrix is
    already proven for get_brand_role in Phase B tests)."""

    def test_capability_tiers(self):
        from ecentric_workspace.alerts import permissions as perms
        orig = perms.get_brand_role
        try:
            for role, manage, activate, review in (
                ("kam", True, False, True),
                ("manager", True, True, True),
                ("leader", False, True, True),
                ("supervisor", True, True, True),
                (None, False, False, False),
            ):
                perms.get_brand_role = lambda u, b, _r=role: _r
                self.assertEqual(perms.can_manage_policy("u", "B"), manage, role)
                self.assertEqual(perms.can_activate_rule("u", "B"), activate, role)
                self.assertEqual(perms.can_review_lock("u", "B"), review, role)
        finally:
            perms.get_brand_role = orig


class TestSourceGuards(unittest.TestCase):
    def test_engine_uses_overlay_with_failsafe(self):
        import inspect
        from ecentric_workspace.alerts.services import alert_engine, rule_overlay as ro
        body = inspect.getsource(alert_engine.check_order_log)
        self.assertIn("rule_overlay.find_rules", body)
        self.assertIn("lock_narrowing", body)
        self.assertIn("return {}  # fail-safe", inspect.getsource(ro.find_rules))

    def test_review_action_is_dry_run_only(self):
        import inspect
        from ecentric_workspace.alerts import api_actions
        body = inspect.getsource(api_actions.review_action)
        for forbidden in ("OmisellClient", "requests", "buffer", "adjust"):
            self.assertNotIn(forbidden, body)
        self.assertIn("Cancelled", body)
